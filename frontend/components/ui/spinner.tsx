import { cn } from "@/lib/utils";

interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {}

export function Spinner({ className, ...props }: SpinnerProps) {
  return (
    <div
      className={cn(
        "h-5 w-5 animate-spin rounded-full border-2 border-primary/60 border-t-transparent",
        className
      )}
      {...props}
    />
  );
}
