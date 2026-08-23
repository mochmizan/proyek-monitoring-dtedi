import { create } from 'zustand';

interface AppUiState {
  // Client UI Preferences
  sidebarOpen: boolean;
  selectedRoomId: string | null;
  setSidebarOpen: (open: boolean) => void;
  setSelectedRoomId: (id: string | null) => void;
}

export const useAppStore = create<AppUiState>((set) => ({
  sidebarOpen: true,
  selectedRoomId: null,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSelectedRoomId: (id) => set({ selectedRoomId: id }),
}));
