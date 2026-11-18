#pragma once
#include <stdint.h>

// 第三方自动换挡包用的「逻辑总线」与物理总线无关，而是按帧 ID 归类：
//   0x229 / 0x678 模板帧      -> 0
//   0x255 / 0x12B 原车配对帧  -> 2
//   其余（挡位、刹车、雷达…） -> 1
// 这样无论帧从 CAN A 还是 CAN B 进来，落到观察器里都是它期望的那一路。
static inline uint8_t autoShiftLogicalBus(uint16_t id) {
  if (id == 0x229 || id == 0x678) return 0;
  if (id == 0x255 || id == 0x12B) return 2;
  return 1;
}
