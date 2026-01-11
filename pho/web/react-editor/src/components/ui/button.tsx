import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

// ============================================================================
// Button Variants
// ============================================================================

const buttonVariants = cva(
  // Base styles
  'inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition-all cursor-pointer disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20',
  {
    variants: {
      variant: {
        default: 'bg-primary text-white hover:bg-primary/90 shadow-sm',
        destructive: 'bg-red-500 text-white hover:bg-red-600 shadow-sm',
        outline: 'border border-border bg-background hover:bg-muted',
        secondary: 'bg-muted text-text hover:bg-muted/80',
        ghost: 'hover:bg-muted',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        xs: 'h-7 px-2 text-xs',
        sm: 'h-8 px-3 text-sm',
        default: 'h-9 px-4',
        lg: 'h-10 px-6 text-base',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

// ============================================================================
// Button Interface
// ============================================================================

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

// ============================================================================
// Button Component
// ============================================================================

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';

// ============================================================================
// Icon Button Component
// ============================================================================

export interface IconButtonProps extends Omit<ButtonProps, 'children'> {
  icon: React.ReactNode;
  label: string;
}

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, icon, label, size = 'icon', variant = 'ghost', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        aria-label={label}
        title={label}
        {...props}
      >
        {icon}
      </button>
    );
  }
);
IconButton.displayName = 'IconButton';

// ============================================================================
// Exports
// ============================================================================

export { Button, buttonVariants };
