import * as React from "react"
import { Dialog as DialogPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"

export function AlertDialog({ open, onOpenChange, children }: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <Dialog open={open} onOpenChange={onOpenChange}>{children}</Dialog>
}
export function AlertDialogContent({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return <DialogContent className={cn("border-red-900/40", className)} {...props} />
}
export function AlertDialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <DialogHeader className={cn(className)} {...props} />
}
export function AlertDialogTitle(props: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogTitle {...props} />
}
export function AlertDialogDescription(props: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return <DialogDescription {...props} />
}
export function AlertDialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <DialogFooter className={cn(className)} {...props} />
}
export function AlertDialogAction({ className, ...props }: React.ComponentProps<typeof Button>) {
  return <Button className={cn("bg-red-600 hover:bg-red-500", className)} {...props} />
}
export function AlertDialogCancel(props: React.ComponentProps<typeof Button>) {
  return <Button variant="outline" {...props} />
}
