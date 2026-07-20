#include <gtest/gtest.h>
#include "friday_nav_layers/terrain_layer.hpp"

using friday_nav_layers::TerrainLayer;

// Nav2 cost constants (hardcoded to avoid a nav2_costmap_2d dep in this unit test)
static constexpr unsigned char FREE_SPACE    =   0u;
static constexpr unsigned char LETHAL        = 254u;
static constexpr unsigned char NO_INFORMATION = 255u;

TEST(TerrainValueToCost, UnknownIsNoInformation)
{
  EXPECT_EQ(TerrainLayer::terrainValueToCost(-1), NO_INFORMATION);
}

TEST(TerrainValueToCost, FlatIsFreeSpace)
{
  EXPECT_EQ(TerrainLayer::terrainValueToCost(0), FREE_SPACE);
}

TEST(TerrainValueToCost, LethalIsLethalObstacle)
{
  EXPECT_EQ(TerrainLayer::terrainValueToCost(100), LETHAL);
}

TEST(TerrainValueToCost, GentleSlopeGradient)
{
  // 40 * 252 / 100 = 100.8 -> round -> 101
  EXPECT_EQ(TerrainLayer::terrainValueToCost(40), 101u);
}

TEST(TerrainValueToCost, RoughGradient)
{
  // 60 * 252 / 100 = 151.2 -> round -> 151
  EXPECT_EQ(TerrainLayer::terrainValueToCost(60), 151u);
}

TEST(TerrainValueToCost, SteepGradient)
{
  // 70 * 252 / 100 = 176.4 -> round -> 176
  EXPECT_EQ(TerrainLayer::terrainValueToCost(70), 176u);
}

TEST(TerrainValueToCost, CappedBelow252)
{
  // 99 * 252 / 100 = 249.48 -> 249 — well below 252
  unsigned char cost = TerrainLayer::terrainValueToCost(99);
  EXPECT_LE(cost, 252u);
  EXPECT_GT(cost, 0u);
}

TEST(TerrainValueToCost, NeverReturns253Or254ForSubLethal)
{
  // Values 1-99 must not produce INSCRIBED (253) or LETHAL (254)
  for (int8_t v = 1; v < 100; ++v) {
    unsigned char cost = TerrainLayer::terrainValueToCost(v);
    EXPECT_LE(cost, 252u) << "value=" << static_cast<int>(v);
    EXPECT_GT(cost, 0u)   << "value=" << static_cast<int>(v);
  }
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
