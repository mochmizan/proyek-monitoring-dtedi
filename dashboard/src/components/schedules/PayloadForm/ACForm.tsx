import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface Props {
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
  disabled?: boolean
}

export default function ACForm({ value, onChange, disabled }: Props) {
  const target = (value.target as string) ?? "AC1"
  const action = (value.action as string) ?? "ON"
  const temp = value.temp as number | undefined

  const set = (patch: Record<string, unknown>) => onChange({ ...value, ...patch })

  return (
    <div className="space-y-3 rounded border border-zinc-800 bg-zinc-950 p-3">
      <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">AC Command</p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="mb-1.5 block text-xs">Target</Label>
          <Select value={target} onValueChange={(v) => set({ target: v })} disabled={disabled}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="AC1">AC1</SelectItem>
                <SelectItem value="AC2">AC2</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1.5 block text-xs">Action</Label>
          <Select value={action} onValueChange={(v) => {
            if (v === "SET_TEMP") set({ action: v, temp: temp ?? 24 })
            else { const nxt: Record<string, unknown> = { ...value, action: v }; delete nxt.temp; onChange(nxt) }
          }} disabled={disabled}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="ON">ON</SelectItem>
                <SelectItem value="OFF">OFF</SelectItem>
                <SelectItem value="SET_TEMP">SET_TEMP</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </div>
      {action === "SET_TEMP" && (
        <div>
          <Label className="mb-1.5 block text-xs">Temp (16-30)</Label>
          <Input type="number" min={16} max={30} value={temp ?? 24} onChange={(e) => set({ temp: parseInt(e.target.value || "24", 10) })} disabled={disabled} />
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        <button type="button" onClick={() => onChange({ target: "AC1", action: "ON" })} className="px-2 py-1 rounded border text-[11px] bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800">AC1 ON</button>
        <button type="button" onClick={() => onChange({ target: "AC1", action: "OFF" })} className="px-2 py-1 rounded border text-[11px] bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800">AC1 OFF</button>
        <button type="button" onClick={() => onChange({ target: "AC1", action: "SET_TEMP", temp: 24 })} className="px-2 py-1 rounded border text-[11px] bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800">AC1 24C</button>
        <button type="button" onClick={() => onChange({ target: "AC2", action: "ON" })} className="px-2 py-1 rounded border text-[11px] bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800">AC2 ON</button>
        <button type="button" onClick={() => onChange({ target: "AC2", action: "SET_TEMP", temp: 24 })} className="px-2 py-1 rounded border text-[11px] bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800">AC2 24C</button>
      </div>
      <div className="bg-zinc-900 border border-zinc-800 rounded p-2 text-xs font-mono text-indigo-300">{JSON.stringify(value)}</div>
    </div>
  )
}
