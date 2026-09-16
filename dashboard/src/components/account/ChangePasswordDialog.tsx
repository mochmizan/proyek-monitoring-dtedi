import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { KeyRound, Loader2 } from 'lucide-react';
import { changePassword } from '@/lib/api';
import { toast, parseApiError } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';

export interface ChangePasswordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Dipanggil setelah password berhasil diganti. Backend mencabut semua
  // sesi aktif saat password diganti, jadi pemanggil sebaiknya
  // langsung logout / arahkan user ke halaman login lagi.
  onSuccess?: () => void;
}

export default function ChangePasswordDialog({ open, onOpenChange, onSuccess }: ChangePasswordDialogProps) {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: changePassword,
    onSuccess: () => {
      toast.success('Password berhasil diganti', {
        description: 'Silakan login ulang menggunakan password baru Anda.',
      });
      resetForm();
      onOpenChange(false);
      onSuccess?.();
    },
    onError: (err) => {
      setFormError(parseApiError(err));
    },
  });

  const resetForm = () => {
    setOldPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setFormError(null);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) resetForm();
    onOpenChange(next);
  };

  const validate = (): string | null => {
    if (!oldPassword.trim() || !newPassword.trim() || !confirmPassword.trim()) {
      return 'Semua kolom wajib diisi';
    }
    if (newPassword.length < 10) return 'Password baru minimal 10 karakter';
    if (newPassword !== confirmPassword) return 'Konfirmasi password baru tidak cocok';
    if (newPassword === oldPassword) return 'Password baru tidak boleh sama dengan password lama';
    return null;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const err = validate();
    if (err) {
      setFormError(err);
      return;
    }
    setFormError(null);
    mutation.mutate({ old_password: oldPassword, new_password: newPassword });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-indigo-400" />
              Ganti Password
            </DialogTitle>
            <DialogDescription>
              Setelah berhasil, semua sesi aktif Anda akan dicabut dan Anda perlu login ulang.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {formError && (
              <p className="text-sm text-destructive" role="alert">
                {formError}
              </p>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="old-password">Password Saat Ini</Label>
              <Input
                id="old-password"
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                disabled={mutation.isPending}
                autoComplete="current-password"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="new-password">Password Baru</Label>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                disabled={mutation.isPending}
                autoComplete="new-password"
                placeholder="Minimal 10 karakter"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm-password">Konfirmasi Password Baru</Label>
              <Input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={mutation.isPending}
                autoComplete="new-password"
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={mutation.isPending}>
              Batal
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Menyimpan...
                </>
              ) : (
                'Ganti Password'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
