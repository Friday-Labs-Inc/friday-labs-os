#pragma once

#include <nav2_costmap_2d/layer.hpp>
#include <nav2_costmap_2d/layered_costmap.hpp>
#include <nav_msgs/msg/occupancy_grid.hpp>
#include <tf2_ros/buffer.h>
#include <tf2/exceptions.h>
#include <rclcpp/rclcpp.hpp>

#include <mutex>
#include <memory>
#include <string>

namespace friday_nav_layers
{

class TerrainLayer : public nav2_costmap_2d::Layer
{
public:
  TerrainLayer() = default;
  ~TerrainLayer() override = default;

  void onInitialize() override;

  void updateBounds(
    double robot_x, double robot_y, double robot_yaw,
    double * min_x, double * min_y, double * max_x, double * max_y) override;

  void updateCosts(
    nav2_costmap_2d::Costmap2D & master_grid,
    int min_i, int min_j, int max_i, int max_j) override;

  void reset() override;

  bool isClearable() override { return true; }

  void matchSize() override {}

  // Pure mapping function — exposed static for unit testing.
  // Returns the Nav2 cost byte for a given terrain OccupancyGrid value:
  //   -1 (unknown)  -> 255 (NO_INFORMATION, caller should skip)
  //    0 (flat)     ->   0 (FREE_SPACE)
  //   1-99 (slope)  -> round(val * 252 / 100), capped at 252
  //  100 (lethal)   -> 254 (LETHAL_OBSTACLE)
  static unsigned char terrainValueToCost(int8_t terrain_value);

private:
  void gridCallback(const nav_msgs::msg::OccupancyGrid::SharedPtr msg);

  rclcpp::Subscription<nav_msgs::msg::OccupancyGrid>::SharedPtr grid_sub_;
  nav_msgs::msg::OccupancyGrid::SharedPtr latest_grid_;
  std::mutex grid_mutex_;

  std::string topic_;
};

}  // namespace friday_nav_layers
