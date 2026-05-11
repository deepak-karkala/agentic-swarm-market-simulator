import { useRef, useEffect, useCallback } from "react";
import styles from "./SwarmCanvas.module.css";

export interface AgentDot {
  id: string;
  group: "consumer" | "competitor" | "analyst" | "kol";
  x: number;
  y: number;
}

interface SwarmCanvasProps {
  agents: AgentDot[];
  round?: number;
}

const GROUP_COLORS = {
  consumer: "--ink2",
  competitor: "--neg",
  analyst: "--accent",
  kol: "--pos",
} as const;

const KOL_RADIUS = 4;
const DOT_RADIUS = 2.5;

export function SwarmCanvas({ agents, round }: SwarmCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const positionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());

  const readColor = useCallback((varName: string): string => {
    const style = getComputedStyle(document.documentElement);
    return style.getPropertyValue(varName).trim() || "#888";
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Initialize positions for new agents
    const existing = positionsRef.current;
    for (const a of agents) {
      if (!existing.has(a.id)) {
        existing.set(a.id, {
          x: Math.random() * canvas.width,
          y: Math.random() * canvas.height,
        });
      }
    }
    // Remove positions for agents that no longer exist
    for (const key of existing.keys()) {
      if (!agents.find((a) => a.id === key)) {
        existing.delete(key);
      }
    }

    const draw = () => {
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      for (const agent of agents) {
        const pos = existing.get(agent.id);
        if (!pos) continue;

        // Gentle random walk
        pos.x += (Math.random() - 0.5) * 2;
        pos.y += (Math.random() - 0.5) * 2;
        pos.x = Math.max(0, Math.min(w, pos.x));
        pos.y = Math.max(0, Math.min(h, pos.y));

        const color = readColor(GROUP_COLORS[agent.group]);
        const radius = agent.group === "kol" ? KOL_RADIUS : DOT_RADIUS;

        ctx.beginPath();
        ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      }

      frameRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(frameRef.current);
  }, [agents, readColor]);

  // Resize canvas to fill container
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={styles.canvas}
      aria-label={`Simulation swarm canvas — ${agents.length} agents, round ${round ?? 0}`}
    />
  );
}
