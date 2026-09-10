"use client";

import { motion } from "framer-motion";
import { cx } from "./ui/primitives";

export function StaggerList({
  items,
  className,
  delay = 0.05,
}: {
  items: React.ReactNode[];
  className?: string;
  delay?: number;
}) {
  return (
    <ul className={cx("space-y-[11px]", className)}>
      {items.map((item, i) => (
        <motion.li
          key={i}
          initial={{ opacity: 0, y: 4 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ delay: i * delay, duration: 0.35 }}
        >
          {item}
        </motion.li>
      ))}
    </ul>
  );
}

export function FadeIn({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ delay, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
