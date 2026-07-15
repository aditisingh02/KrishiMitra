"use client";
import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import { motion } from "framer-motion";
import React from "react";

/* ------------------------------- Button ---------------------------------- */
const buttonStyles = cva(
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all duration-200 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/15 disabled:opacity-40 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary: "bg-ink text-paper hover:bg-charcoal",
        outline: "border border-line bg-surface text-charcoal hover:border-faint/50 hover:bg-bone",
        ghost: "text-charcoal hover:bg-bone",
      },
      size: {
        sm: "h-9 px-3.5 text-sm",
        md: "h-10 px-5 text-sm",
        lg: "h-12 px-6 text-[15px]",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonStyles> {}

export function Button({ className, variant, size, children, ...props }: ButtonProps) {
  return (
    <button className={cn(buttonStyles({ variant, size }), className)} {...props}>
      {children}
    </button>
  );
}

/* -------------------------------- Tag ------------------------------------ */
const tagTones: Record<string, string> = {
  green: "bg-pale-green text-pale-greenink",
  blue: "bg-pale-blue text-pale-blueink",
  red: "bg-pale-red text-pale-redink",
  yellow: "bg-pale-yellow text-pale-yellowink",
  neutral: "bg-bone text-muted",
};

export function Tag({
  children,
  tone = "neutral",
  className,
  dot,
}: {
  children: React.ReactNode;
  tone?: keyof typeof tagTones;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span className={cn("tag", tagTones[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />}
      {children}
    </span>
  );
}

/* ------------------------------- Card ------------------------------------ */
export function Card({
  children,
  className,
  delay = 0,
  interactive = true,
  as,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  interactive?: boolean;
  as?: "div" | "section";
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.6, delay, ease: [0.16, 1, 0.3, 1] }}
      className={cn("card p-6", interactive && "card-interactive", className)}
    >
      {children}
    </motion.div>
  );
}

/* --------------------------- Section heading ----------------------------- */
export function SectionTitle({
  eyebrow,
  title,
  subtitle,
  className,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  className?: string;
}) {
  return (
    <div className={cn("mb-6", className)}>
      {eyebrow && <p className="overline mb-2">{eyebrow}</p>}
      <h2 className="display text-2xl text-ink md:text-3xl">{title}</h2>
      {subtitle && <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">{subtitle}</p>}
    </div>
  );
}
