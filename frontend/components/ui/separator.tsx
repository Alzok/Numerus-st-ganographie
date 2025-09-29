import * as React from "react";
import { cn } from "@/lib/utils";

const Separator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("h-px w-full bg-gradient-to-r from-transparent via-border/50 to-transparent", className)}
      {...props}
    />
  )
);
Separator.displayName = "Separator";

export { Separator };
