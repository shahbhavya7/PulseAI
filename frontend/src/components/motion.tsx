"use client";

import { motion, type Variants } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Shared easing/timing so motion feels consistent across the app. */
const EASE = [0.16, 1, 0.3, 1] as const;

/** Container that fades/slides its children in with a stagger. Pair with
 *  <MotionItem> for each child. */
const containerVariants: Variants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.09, delayChildren: 0.05 },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 24, scale: 0.97 },
  show: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.55, ease: EASE },
  },
};

export function MotionStagger({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function MotionItem({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div variants={itemVariants} className={className}>
      {children}
    </motion.div>
  );
}

/** A whole route's content: fades + slides up on mount. */
export function PageTransition({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Glass card that lifts on hover and springs in on mount. */
export function MotionCard({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.55, ease: EASE, delay }}
      whileHover={{ y: -4, scale: 1.006 }}
      className={cn("glass glass-hover rounded-[var(--radius)]", className)}
    >
      {children}
    </motion.div>
  );
}
