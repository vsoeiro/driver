import { cva } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-sm border px-2 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'border-border/90 bg-muted/30 text-muted-foreground',
        secondary: 'border-border/95 bg-secondary/70 text-secondary-foreground',
        outline: 'text-foreground',
        destructive: 'border-destructive/40 bg-destructive/8 text-destructive',
        success: 'border-emerald-300 bg-emerald-50 text-emerald-800',
        warning: 'border-amber-300 bg-amber-50 text-amber-800',
        info: 'border-sky-300 bg-sky-50 text-sky-700',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

function Badge({ className, variant, ...props }) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
