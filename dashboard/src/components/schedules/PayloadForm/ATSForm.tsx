import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface Props {
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
  disabled?: boolean
}

export default function ATSForm({ value, onChange, disabled }: Props) {
  const mode = (value.mode as string) ?? ""
  const sgm = (value.start_genset as string) ?? ""
  const rst = (value.reset as string) ?? ""

  const set = (patch: Record<string, unknown>) => {
    const next: Record<string, unknown> = { ...value, ...patch }
    // remove empty
    Object.keys(next).forEach((k) => { if (next[k] === "" || next[k] === undefined) delete next[k] })
    onChange(next)
  }
  const clear = (k: string) => {
    const next = { ...value }
    delete next[k]
    onChange(next)
  }

  return (
    <div className="space-y-3 rounded border border-zinc-800 bg-zinc-950 p-3">
      <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">ATS Command</p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="mb-1.5 block text-xs">Mode</Label>
          <Select value={mode || "__none"} onValueChange={(v) => v === "__none" ? clear("mode") : set({ mode: v })} disabled={disabled}>
            <SelectTrigger className="w-full"><SelectValue placeholder="—" /></SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="__none">— none —</SelectItem>
                <SelectItem value="auto">auto</SelectItem>
                <SelectItem value="manual">manual</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1.5 block text-xs">Genset</Label>
          <Select value={sgm || "__none"} onValueChange={(v) => v === "__none" ? clear("start_genset") : set({ start_genset: v })} disabled={disabled}>
            <SelectTrigger className="w-full"><SelectValue placeholder="—" /></SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="__none">— none —</SelectItem>
                <SelectItem value="on">on</SelectItem>
                <SelectItem value="off">off</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div>
        <Label className="mb-1.5 block text-xs">Reset</Label>
        <Select value={rst || "__none"} onValueChange={(v) => v === "__none" ? clear("reset") : set({ reset: v })} disabled={disabled}>
          <SelectTrigger className="w-full"><SelectValue placeholder="—" /></SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="__none">— none —</SelectItem>
              <SelectItem value="rst">rst</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <button type="button" onClick={() => onChange({ mode: "manual", start_genset: "on" })} className="px-2 py-1 rounded border text-[11px] bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800">Warmup manual+on</button>
        <button type="button" onClick={() => onChange({ mode: "auto" })} className="px-2 py-1 rounded border text-[11px] bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800">Auto</button>
        <button type="button" onClick={() => onChange({ reset: "rst" })} className="px-2 py-1 rounded border text-[11px] bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800">Reset</button>
      </div>
      <p className="text-[11px] text-zinc-500">At least one field required. Bundled warmup is <code className="bg-zinc-900 px-1 rounded">manual+on</code>.</p>
      <div className="bg-zinc-900 border border-zinc-800 rounded p-2 text-xs font-mono text-indigo-300">{JSON.stringify(value) || "{}"}</div>
    </div>
  )
}
