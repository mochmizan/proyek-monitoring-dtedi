export type Role = 'Admin' | 'Operator' | 'Viewer';

export interface User {
  username: string;
  displayName: string;
  role: Role;
  createdAt: string;
}

export type DeviceType = 'Temperature' | 'ATS' | 'AC';
export type DeviceStatus = 'Online' | 'Offline';

export interface PendingChanges {
  samplingInterval: number | null;
  warningThreshold: number | null;
  criticalThreshold: number | null;
  telegramAlerts: boolean | null;
  hysteresis: number | null;
  debounce: number | null;
}

export interface Device {
  id: string;
  name: string;
  type: DeviceType;
  macAddress: string;
  roomId: string | null;
  status: DeviceStatus;
  lastReading: string;
  lastSeen: string;
  firmwareVersion: string;
  samplingInterval: number;
  warningThreshold: number | null;
  criticalThreshold: number | null;
  telegramAlerts: boolean;
  pendingChanges: PendingChanges | null;
  mapX: number | null; // percentage on map (0-100)
  mapY: number | null; // percentage on map (0-100)
  hysteresis: number | null;
  debounce: number | null;
}

export interface Room {
  id: string;
  name: string;
  status: 'Normal' | 'Warning' | 'Critical' | 'Offline';
  deviceCount: number;
  lastUpdate: string;
}

export interface Alert {
  id: string;
  timestamp: string;
  severity: 'Warning' | 'Critical';
  deviceId: string;
  deviceName: string;
  roomId: string;
  roomName: string;
  parameter: string;
  value: string;
  threshold: string;
}

export interface Reading {
  id: string;
  deviceId: string;
  timestamp: string;
  value: number | string;
}

export interface ACState {
  power: boolean;
  setpoint: number;
}

export const INITIAL_USERS: User[] = [
  {
    username: 'admin',
    displayName: 'Jane Doe (Admin)',
    role: 'Admin',
    createdAt: '2026-06-01T08:00:00Z',
  },
  {
    username: 'operator',
    displayName: 'John Smith (Operator)',
    role: 'Operator',
    createdAt: '2026-06-15T09:30:00Z',
  },
  {
    username: 'viewer',
    displayName: 'Alice Johnson (Viewer)',
    role: 'Viewer',
    createdAt: '2026-07-01T12:00:00Z',
  },
];

export const INITIAL_ROOMS: Room[] = [
  {
    id: 'server-room',
    name: 'Server Room',
    status: 'Normal',
    deviceCount: 3,
    lastUpdate: '10s ago',
  },
  {
    id: 'network-closet',
    name: 'Network Closet',
    status: 'Warning',
    deviceCount: 1,
    lastUpdate: '25s ago',
  },
  {
    id: 'battery-room',
    name: 'Battery Room',
    status: 'Critical',
    deviceCount: 1,
    lastUpdate: '5s ago',
  },
  {
    id: 'office-area',
    name: 'Office Area',
    status: 'Normal',
    deviceCount: 2,
    lastUpdate: '15s ago',
  },
  {
    id: 'warehouse',
    name: 'Warehouse',
    status: 'Offline',
    deviceCount: 0,
    lastUpdate: 'Never',
  },
];

export const INITIAL_DEVICES: Device[] = [
  {
    id: 'temp-1',
    name: 'Server Room Temp A',
    type: 'Temperature',
    macAddress: '00:1A:2B:3C:4D:5E',
    roomId: 'server-room',
    status: 'Online',
    lastReading: '22.4°C',
    lastSeen: '10s ago',
    firmwareVersion: 'v1.4.2',
    samplingInterval: 30,
    warningThreshold: 28,
    criticalThreshold: 35,
    telegramAlerts: true,
    pendingChanges: {
      samplingInterval: 10,
      warningThreshold: 28,
      criticalThreshold: 35,
      telegramAlerts: true,
      hysteresis: 1.5,
      debounce: 3,
    },
    mapX: 35.5,
    mapY: 42.0,
    hysteresis: 1.0,
    debounce: 3,
  },
  {
    id: 'ats-1',
    name: 'Server Room ATS',
    type: 'ATS',
    macAddress: '00:1A:2B:3C:4D:5F',
    roomId: 'server-room',
    status: 'Online',
    lastReading: 'PLN (Grid)',
    lastSeen: '10s ago',
    firmwareVersion: 'v2.1.0',
    samplingInterval: 60,
    warningThreshold: null,
    criticalThreshold: null,
    telegramAlerts: true,
    pendingChanges: null,
    mapX: 45.0,
    mapY: 30.5,
    hysteresis: null,
    debounce: null,
  },
  {
    id: 'ac-1',
    name: 'Server Room AC',
    type: 'AC',
    macAddress: '00:1A:2B:3C:4D:60',
    roomId: 'server-room',
    status: 'Online',
    lastReading: 'AC On 21°C',
    lastSeen: '10s ago',
    firmwareVersion: 'v1.0.8',
    samplingInterval: 60,
    warningThreshold: null,
    criticalThreshold: null,
    telegramAlerts: false,
    pendingChanges: null,
    mapX: 52.0,
    mapY: 45.0,
    hysteresis: null,
    debounce: null,
  },
  {
    id: 'temp-2',
    name: 'Network Closet Temp',
    type: 'Temperature',
    macAddress: '00:1A:2B:3C:4D:61',
    roomId: 'network-closet',
    status: 'Online',
    lastReading: '31.2°C',
    lastSeen: '25s ago',
    firmwareVersion: 'v1.4.2',
    samplingInterval: 30,
    warningThreshold: 30,
    criticalThreshold: 35,
    telegramAlerts: false,
    pendingChanges: null,
    mapX: 70.0,
    mapY: 20.0,
    hysteresis: 1.0,
    debounce: 3,
  },
  {
    id: 'temp-3',
    name: 'Battery Room Temp',
    type: 'Temperature',
    macAddress: '00:1A:2B:3C:4D:62',
    roomId: 'battery-room',
    status: 'Online',
    lastReading: '36.8°C',
    lastSeen: '5s ago',
    firmwareVersion: 'v1.4.2',
    samplingInterval: 15,
    warningThreshold: 30,
    criticalThreshold: 35,
    telegramAlerts: true,
    pendingChanges: null,
    mapX: 20.0,
    mapY: 75.0,
    hysteresis: 1.0,
    debounce: 3,
  },
  {
    id: 'temp-4',
    name: 'Office Area Temp',
    type: 'Temperature',
    macAddress: '00:1A:2B:3C:4D:63',
    roomId: 'office-area',
    status: 'Online',
    lastReading: '24.1°C',
    lastSeen: '15s ago',
    firmwareVersion: 'v1.4.2',
    samplingInterval: 30,
    warningThreshold: 26,
    criticalThreshold: 30,
    telegramAlerts: false,
    pendingChanges: null,
    mapX: 85.0,
    mapY: 60.0,
    hysteresis: 1.0,
    debounce: 3,
  },
  {
    id: 'ac-2',
    name: 'Office Area AC',
    type: 'AC',
    macAddress: '00:1A:2B:3C:4D:64',
    roomId: 'office-area',
    status: 'Online',
    lastReading: 'AC Off',
    lastSeen: '15s ago',
    firmwareVersion: 'v1.0.8',
    samplingInterval: 60,
    warningThreshold: null,
    criticalThreshold: null,
    telegramAlerts: false,
    pendingChanges: null,
    mapX: 80.0,
    mapY: 50.0,
    hysteresis: null,
    debounce: null,
  },
  // Unpaired devices
  {
    id: 'temp-unpaired-1',
    name: 'Unpaired Temp Sensor 1',
    type: 'Temperature',
    macAddress: 'AA:BB:CC:DD:EE:01',
    roomId: null,
    status: 'Online',
    lastReading: '25.0°C',
    lastSeen: '1m ago',
    firmwareVersion: 'v1.4.2',
    samplingInterval: 30,
    warningThreshold: 30,
    criticalThreshold: 35,
    telegramAlerts: false,
    pendingChanges: null,
    mapX: null,
    mapY: null,
    hysteresis: 1.0,
    debounce: 3,
  },
  {
    id: 'ats-unpaired-1',
    name: 'Unpaired ATS Module',
    type: 'ATS',
    macAddress: 'AA:BB:CC:DD:EE:02',
    roomId: null,
    status: 'Offline',
    lastReading: 'Unknown',
    lastSeen: '2h ago',
    firmwareVersion: 'v2.1.0',
    samplingInterval: 60,
    warningThreshold: null,
    criticalThreshold: null,
    telegramAlerts: false,
    pendingChanges: null,
    mapX: null,
    mapY: null,
    hysteresis: null,
    debounce: null,
  },
];

export const INITIAL_ALERTS: Alert[] = [
  {
    id: 'alert-1',
    timestamp: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
    severity: 'Critical',
    deviceId: 'temp-3',
    deviceName: 'Battery Room Temp',
    roomId: 'battery-room',
    roomName: 'Battery Room',
    parameter: 'Temperature',
    value: '37.2°C',
    threshold: '> 35°C (critical)',
  },
  {
    id: 'alert-2',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-1',
    deviceName: 'Server Room Temp A',
    roomId: 'server-room',
    roomName: 'Server Room',
    parameter: 'Temperature',
    value: '28.5°C',
    threshold: '> 28°C (warning)',
  },
  {
    id: 'alert-3',
    timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-2',
    deviceName: 'Network Closet Temp',
    roomId: 'network-closet',
    roomName: 'Network Closet',
    parameter: 'Temperature',
    value: '30.5°C',
    threshold: '> 30°C (warning)',
  },
  {
    id: 'alert-4',
    timestamp: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
    severity: 'Critical',
    deviceId: 'ats-1',
    deviceName: 'Server Room ATS',
    roomId: 'server-room',
    roomName: 'Server Room',
    parameter: 'Power Source',
    value: 'PLN Lost',
    threshold: 'Grid Fail',
  },
  {
    id: 'alert-5',
    timestamp: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-4',
    deviceName: 'Office Area Temp',
    roomId: 'office-area',
    roomName: 'Office Area',
    parameter: 'Temperature',
    value: '26.3°C',
    threshold: '> 26°C (warning)',
  },
  {
    id: 'alert-6',
    timestamp: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
    severity: 'Critical',
    deviceId: 'temp-3',
    deviceName: 'Battery Room Temp',
    roomId: 'battery-room',
    roomName: 'Battery Room',
    parameter: 'Temperature',
    value: '36.1°C',
    threshold: '> 35°C (critical)',
  },
  {
    id: 'alert-7',
    timestamp: new Date(Date.now() - 18 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-1',
    deviceName: 'Server Room Temp A',
    roomId: 'server-room',
    roomName: 'Server Room',
    parameter: 'Temperature',
    value: '28.1°C',
    threshold: '> 28°C (warning)',
  },
  {
    id: 'alert-8',
    timestamp: new Date(Date.now() - 36 * 60 * 60 * 1000).toISOString(),
    severity: 'Critical',
    deviceId: 'temp-3',
    deviceName: 'Battery Room Temp',
    roomId: 'battery-room',
    roomName: 'Battery Room',
    parameter: 'Temperature',
    value: '35.8°C',
    threshold: '> 35°C (critical)',
  },
  {
    id: 'alert-9',
    timestamp: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-2',
    deviceName: 'Network Closet Temp',
    roomId: 'network-closet',
    roomName: 'Network Closet',
    parameter: 'Temperature',
    value: '30.1°C',
    threshold: '> 30°C (warning)',
  },
  {
    id: 'alert-10',
    timestamp: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Critical',
    deviceId: 'ats-1',
    deviceName: 'Server Room ATS',
    roomId: 'server-room',
    roomName: 'Server Room',
    parameter: 'Power Source',
    value: 'PLN Lost',
    threshold: 'Grid Fail',
  },
  {
    id: 'alert-11',
    timestamp: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-4',
    deviceName: 'Office Area Temp',
    roomId: 'office-area',
    roomName: 'Office Area',
    parameter: 'Temperature',
    value: '26.7°C',
    threshold: '> 26°C (warning)',
  },
  {
    id: 'alert-12',
    timestamp: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-1',
    deviceName: 'Server Room Temp A',
    roomId: 'server-room',
    roomName: 'Server Room',
    parameter: 'Temperature',
    value: '28.4°C',
    threshold: '> 28°C (warning)',
  },
  {
    id: 'alert-13',
    timestamp: new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Critical',
    deviceId: 'temp-3',
    deviceName: 'Battery Room Temp',
    roomId: 'battery-room',
    roomName: 'Battery Room',
    parameter: 'Temperature',
    value: '36.5°C',
    threshold: '> 35°C (critical)',
  },
  {
    id: 'alert-14',
    timestamp: new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-2',
    deviceName: 'Network Closet Temp',
    roomId: 'network-closet',
    roomName: 'Network Closet',
    parameter: 'Temperature',
    value: '30.8°C',
    threshold: '> 30°C (warning)',
  },
  {
    id: 'alert-15',
    timestamp: new Date(Date.now() - 12 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Critical',
    deviceId: 'temp-3',
    deviceName: 'Battery Room Temp',
    roomId: 'battery-room',
    roomName: 'Battery Room',
    parameter: 'Temperature',
    value: '35.9°C',
    threshold: '> 35°C (critical)',
  },
  {
    id: 'alert-16',
    timestamp: new Date(Date.now() - 15 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-4',
    deviceName: 'Office Area Temp',
    roomId: 'office-area',
    roomName: 'Office Area',
    parameter: 'Temperature',
    value: '26.2°C',
    threshold: '> 26°C (warning)',
  },
  {
    id: 'alert-17',
    timestamp: new Date(Date.now() - 20 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-1',
    deviceName: 'Server Room Temp A',
    roomId: 'server-room',
    roomName: 'Server Room',
    parameter: 'Temperature',
    value: '28.3°C',
    threshold: '> 28°C (warning)',
  },
  {
    id: 'alert-18',
    timestamp: new Date(Date.now() - 25 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Critical',
    deviceId: 'temp-3',
    deviceName: 'Battery Room Temp',
    roomId: 'battery-room',
    roomName: 'Battery Room',
    parameter: 'Temperature',
    value: '36.2°C',
    threshold: '> 35°C (critical)',
  },
  {
    id: 'alert-19',
    timestamp: new Date(Date.now() - 28 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-2',
    deviceName: 'Network Closet Temp',
    roomId: 'network-closet',
    roomName: 'Network Closet',
    parameter: 'Temperature',
    value: '30.3°C',
    threshold: '> 30°C (warning)',
  },
  {
    id: 'alert-20',
    timestamp: new Date(Date.now() - 35 * 24 * 60 * 60 * 1000).toISOString(),
    severity: 'Warning',
    deviceId: 'temp-4',
    deviceName: 'Office Area Temp',
    roomId: 'office-area',
    roomName: 'Office Area',
    parameter: 'Temperature',
    value: '26.5°C',
    threshold: '> 26°C (warning)',
  },
];
