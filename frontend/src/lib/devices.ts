import type { DeviceType } from '../api/types'

/** What a part or build is for; a product without one is general (fits any device). */
export const DEVICE_TYPES: DeviceType[] = [
  'pc',
  'mini_pc',
  'laptop',
  'tablet',
  'nas',
  'workstation',
  'server',
  'smart_ring',
  'health_tracker',
]
