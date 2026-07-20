#include "friday_nav_layers/terrain_layer.hpp"

#include <nav2_costmap_2d/cost_values.hpp>
#include <pluginlib/class_list_macros.hpp>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>

#include <algorithm>
#include <cmath>
#include <stdexcept>

PLUGINLIB_EXPORT_CLASS(friday_nav_layers::TerrainLayer, nav2_costmap_2d::Layer)

namespace friday_nav_layers
{

// ---------------------------------------------------------------------------
// Pure mapping — no Nav2 header needed to test this.
// ---------------------------------------------------------------------------
unsigned char TerrainLayer::terrainValueToCost(int8_t terrain_value)
{
  if (terrain_value < 0) {
    return 255u;  // NO_INFORMATION — caller skips rather than writes
  }
  if (terrain_value == 0) {
    return 0u;    // FREE_SPACE
  }
  if (terrain_value >= 100) {
    return 254u;  // LETHAL_OBSTACLE
  }
  // Scale 1-99 into 1-252 so gradient cells are expensive but plannable.
  // 40 -> 101, 60 -> 151, 70 -> 176
  auto cost = static_cast<unsigned char>(
    std::round(static_cast<double>(terrain_value) * 252.0 / 100.0));
  return std::min(cost, static_cast<unsigned char>(252u));
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
void TerrainLayer::onInitialize()
{
  auto node = node_.lock();
  if (!node) {
    throw std::runtime_error("TerrainLayer: unable to lock node");
  }

  declareParameter("enabled", rclcpp::ParameterValue(true));
  declareParameter("topic", rclcpp::ParameterValue(std::string("/terrain/costmap")));

  node->get_parameter(name_ + ".enabled", enabled_);
  node->get_parameter(name_ + ".topic", topic_);

  // Match the publisher QoS: RELIABLE + TRANSIENT_LOCAL so we receive the
  // last message immediately on subscribe even if published before Nav2 started.
  auto qos = rclcpp::QoS(rclcpp::KeepLast(1)).reliable().transient_local();
  grid_sub_ = node->create_subscription<nav_msgs::msg::OccupancyGrid>(
    topic_, qos,
    [this](const nav_msgs::msg::OccupancyGrid::SharedPtr msg) {
      gridCallback(msg);
    });

  // Mark as current immediately: this is an optional-data layer. If no terrain
  // data has arrived yet we simply write nothing to the master grid — we don't
  // want to block Nav2 planning by holding current_ = false indefinitely.
  current_ = true;

  RCLCPP_INFO(node->get_logger(),
    "TerrainLayer initialized — topic: %s", topic_.c_str());
}

void TerrainLayer::gridCallback(const nav_msgs::msg::OccupancyGrid::SharedPtr msg)
{
  std::lock_guard<std::mutex> lock(grid_mutex_);
  latest_grid_ = msg;
}

void TerrainLayer::reset()
{
  std::lock_guard<std::mutex> lock(grid_mutex_);
  latest_grid_.reset();
  current_ = false;
}

// ---------------------------------------------------------------------------
// updateBounds — expand dirty region to cover the terrain grid footprint
// projected into the global costmap frame via tf2.
// ---------------------------------------------------------------------------
void TerrainLayer::updateBounds(
  double /*robot_x*/, double /*robot_y*/, double /*robot_yaw*/,
  double * min_x, double * min_y, double * max_x, double * max_y)
{
  if (!enabled_) return;

  nav_msgs::msg::OccupancyGrid::SharedPtr grid;
  {
    std::lock_guard<std::mutex> lock(grid_mutex_);
    grid = latest_grid_;
  }
  if (!grid) return;

  const std::string & global_frame = layered_costmap_->getGlobalFrameID();
  const std::string & grid_frame = grid->header.frame_id;

  geometry_msgs::msg::TransformStamped tf_stamped;
  try {
    // grid_frame (base_link) -> global_frame (map or odom)
    tf_stamped = tf_->lookupTransform(global_frame, grid_frame, tf2::TimePointZero);
  } catch (const tf2::TransformException & ex) {
    auto node = node_.lock();
    if (node) {
      RCLCPP_WARN_THROTTLE(node->get_logger(), *node->get_clock(), 2000,
        "TerrainLayer::updateBounds tf %s->%s failed: %s",
        grid_frame.c_str(), global_frame.c_str(), ex.what());
    }
    return;
  }

  // Terrain grid corners in grid_frame (base_link).
  const double ox = grid->info.origin.position.x;
  const double oy = grid->info.origin.position.y;
  const double w  = static_cast<double>(grid->info.width)  * grid->info.resolution;
  const double h  = static_cast<double>(grid->info.height) * grid->info.resolution;

  const std::array<std::pair<double, double>, 4> corners = {{
    {ox,     oy    },
    {ox + w, oy    },
    {ox,     oy + h},
    {ox + w, oy + h},
  }};

  // Extract 2D yaw from the quaternion.
  const auto & q = tf_stamped.transform.rotation;
  const double siny = 2.0 * (q.w * q.z + q.x * q.y);
  const double cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z);
  const double yaw = std::atan2(siny, cosy);
  const double cy  = std::cos(yaw);
  const double sy  = std::sin(yaw);
  const double tx  = tf_stamped.transform.translation.x;
  const double ty  = tf_stamped.transform.translation.y;

  for (const auto & [cx, cy_pt] : corners) {
    const double gx = cy * cx - sy * cy_pt + tx;
    const double gy = sy * cx + cy * cy_pt + ty;
    *min_x = std::min(*min_x, gx);
    *min_y = std::min(*min_y, gy);
    *max_x = std::max(*max_x, gx);
    *max_y = std::max(*max_y, gy);
  }
}

// ---------------------------------------------------------------------------
// updateCosts — write gradient costs into the master grid.
//
// For each cell in the dirty window:
//   1. Find its world position.
//   2. Transform world -> terrain grid frame (base_link) via tf2 (one lookup).
//   3. Compute the terrain grid cell index.
//   4. Map terrain value -> Nav2 cost.
//   5. Apply updateWithMax: only RAISE the master cost, never lower it.
//      Unknown cells (-1) are skipped entirely.
// ---------------------------------------------------------------------------
void TerrainLayer::updateCosts(
  nav2_costmap_2d::Costmap2D & master_grid,
  int min_i, int min_j, int max_i, int max_j)
{
  if (!enabled_) {
    current_ = true;
    return;
  }

  nav_msgs::msg::OccupancyGrid::SharedPtr grid;
  {
    std::lock_guard<std::mutex> lock(grid_mutex_);
    grid = latest_grid_;
  }
  if (!grid) {
    // No terrain data yet — yield current_ so we don't stall other layers.
    current_ = true;
    return;
  }

  const std::string & global_frame = layered_costmap_->getGlobalFrameID();
  const std::string & grid_frame   = grid->header.frame_id;

  geometry_msgs::msg::TransformStamped tf_inv;
  try {
    // global_frame (map/odom) -> grid_frame (base_link)
    tf_inv = tf_->lookupTransform(grid_frame, global_frame, tf2::TimePointZero);
  } catch (const tf2::TransformException & ex) {
    auto node = node_.lock();
    if (node) {
      RCLCPP_WARN_THROTTLE(node->get_logger(), *node->get_clock(), 2000,
        "TerrainLayer::updateCosts tf %s->%s failed: %s",
        global_frame.c_str(), grid_frame.c_str(), ex.what());
    }
    return;
  }

  // Cache the 2D transform: global -> base_link.
  const auto & q  = tf_inv.transform.rotation;
  const double siny = 2.0 * (q.w * q.z + q.x * q.y);
  const double cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z);
  const double yaw = std::atan2(siny, cosy);
  const double cy  = std::cos(yaw);
  const double sy  = std::sin(yaw);
  const double tx  = tf_inv.transform.translation.x;
  const double ty  = tf_inv.transform.translation.y;

  const double           ox    = grid->info.origin.position.x;
  const double           oy    = grid->info.origin.position.y;
  const double           res   = grid->info.resolution;
  const unsigned int     gw    = grid->info.width;
  const unsigned int     gh    = grid->info.height;

  for (int j = min_j; j < max_j; ++j) {
    for (int i = min_i; i < max_i; ++i) {
      double wx, wy;
      master_grid.mapToWorld(
        static_cast<unsigned int>(i),
        static_cast<unsigned int>(j),
        wx, wy);

      // Transform world (global frame) -> terrain grid frame (base_link).
      const double bl_x = cy * wx - sy * wy + tx;
      const double bl_y = sy * wx + cy * wy + ty;

      // Terrain grid cell index.
      const int gc = static_cast<int>(std::floor((bl_x - ox) / res));
      const int gr = static_cast<int>(std::floor((bl_y - oy) / res));

      if (gc < 0 || gr < 0 ||
          static_cast<unsigned int>(gc) >= gw ||
          static_cast<unsigned int>(gr) >= gh) {
        continue;
      }

      const int8_t tv = grid->data[static_cast<size_t>(gr) * gw +
                                   static_cast<size_t>(gc)];

      // Unknown terrain: leave the underlying costmap cell untouched.
      if (tv < 0) continue;

      const unsigned char new_cost = terrainValueToCost(tv);

      // updateWithMax: only raise the master cost, never lower it.
      // Exception: NO_INFORMATION (255) on the master should still accept
      // a FREE_SPACE (0) mark from flat terrain so the planner knows it's clear.
      const unsigned char cur = master_grid.getCost(
        static_cast<unsigned int>(i),
        static_cast<unsigned int>(j));

      if (new_cost == 0u) {
        // FREE_SPACE — only write if master is currently NO_INFORMATION (255);
        // otherwise max(cur, 0) = cur so nothing changes.
        if (cur == 255u) {
          master_grid.setCost(
            static_cast<unsigned int>(i),
            static_cast<unsigned int>(j),
            0u);
        }
      } else if (new_cost > cur) {
        master_grid.setCost(
          static_cast<unsigned int>(i),
          static_cast<unsigned int>(j),
          new_cost);
      }
    }
  }

  current_ = true;
}

}  // namespace friday_nav_layers
