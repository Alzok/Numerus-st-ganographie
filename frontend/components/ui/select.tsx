import * as React from "react";
import { cn } from "@/lib/utils";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(({ className, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "h-11 w-full rounded-xl border border-border/60 bg-secondary/30 px-4 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
      className
    )}
    {...props}
  />
));
Select.displayName = "Select";

export { Select };
