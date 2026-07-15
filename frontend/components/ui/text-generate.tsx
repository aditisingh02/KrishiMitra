"use client";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/** Aceternity-style word-by-word reveal for AI responses. */
export function TextGenerate({
  text,
  className,
  delay = 0,
}: {
  text: string;
  className?: string;
  delay?: number;
}) {
  const words = (text || "").split(" ");
  return (
    <motion.p className={cn("leading-relaxed", className)}>
      {words.map((word, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, filter: "blur(6px)", y: 4 }}
          animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
          transition={{ duration: 0.35, delay: delay + i * 0.02 }}
          className="inline-block"
        >
          {word}&nbsp;
        </motion.span>
      ))}
    </motion.p>
  );
}
