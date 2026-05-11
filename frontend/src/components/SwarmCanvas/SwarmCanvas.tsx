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
  const containerRef = useRef<HTMLDivElement>(null);
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

    const existing = positionsRef.current;
    for (const a of agents) {
      if (!existing.has(a.id)) {
        // Use caller-provided coordinates; scale to canvas if needed
        existing.set(a.id, { x: a.x * canvas.width, y: a.y * canvas.height });
      }
    }
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

        // Gentle random walk delta from the stored position
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

  // ResizeObserver on container for layout-driven resizes (e.g. sidebar collapse)
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resize = () => {
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
    };
    resize();

    const observer = new ResizeObserver(resize);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%" }}>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        aria-label={`Simulation swarm canvas — ${agents.length} agents, round ${round ?? 0}`}
      />
    </div>
  );
}
