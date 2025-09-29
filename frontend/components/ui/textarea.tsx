import * as React from "react";
import { cn } from "@/lib/utils";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        suppressHydrationWarning
        className={cn(
          "flex min-h-[120px] w-full rounded-xl border border-border/60 bg-secondary/40 px-4 py-3 text-sm shadow-inner transition placeholder:text-muted-foreground focus:border-primary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Textarea.displayName = "Textarea";

export { Textarea };
