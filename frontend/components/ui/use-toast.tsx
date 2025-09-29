"use client";

import * as React from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const toastVariants = cva(
  "group pointer-events-auto relative flex w-full items-center justify-between space-x-4 overflow-hidden rounded-2xl border border-border/40 bg-secondary/70 px-5 py-4 text-sm shadow-xl backdrop-blur",
  {
    variants: {
      variant: {
        default: "text-foreground",
        destructive: "border-red-500/50 bg-red-500/20 text-red-200",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

interface Toast extends ToastPrimitive.ToastProps, VariantProps<typeof toastVariants> {
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  id?: string;
}

interface ToastContextValue {
  toast: (toast: Omit<Toast, "open" | "id">) => void;
}

const ToastContext = React.createContext<ToastContextValue | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);

  const toast = React.useCallback((toastProps: Omit<Toast, "open" | "id">) => {
    const cryptoRef = typeof window !== "undefined" ? window.crypto : undefined;
    const id = cryptoRef?.randomUUID ? cryptoRef.randomUUID() : Math.random().toString(36).slice(2);
    setToasts((current) => [
      ...current,
      {
        ...toastProps,
        open: true,
        id,
      } as Toast,
    ]);
  }, []);

  const handleOpenChange = React.useCallback((id: string, open: boolean) => {
    if (!open) {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}
        {toasts.map(({ id, title, description, action, variant, ...props }) => (
          <ToastPrimitive.Root
            key={id}
            className={toastVariants({ variant })}
            onOpenChange={(open) => handleOpenChange(id, open)}
            {...props}
          >
            <div className="grid gap-1">
              {title ? <div className="text-sm font-semibold">{title}</div> : null}
              {description ? <div className="text-sm opacity-80">{description}</div> : null}
            </div>
            {action ? <div className="ml-auto">{action}</div> : null}
            <ToastPrimitive.Close className="absolute right-3 top-3 text-xs uppercase tracking-wide text-muted-foreground">
              Fermer
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed right-4 top-4 z-[100] flex max-h-screen w-full flex-col gap-3 md:max-w-sm" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = React.useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
