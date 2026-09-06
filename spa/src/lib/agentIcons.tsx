import {
  Anchor,
  Atom,
  Bot,
  Compass,
  Cpu,
  Database,
  Eye,
  Feather,
  Flame,
  Globe,
  Hexagon,
  Infinity as InfinityIcon,
  Joystick,
  Key,
  Lightbulb,
  Magnet,
  Network,
  Orbit,
  Puzzle,
  Radar,
  Sparkles,
  Telescope,
  Umbrella,
  Video,
  Wand2,
  Zap,
  type LucideIcon,
} from "lucide-react";

const AGENT_ICON_SET: LucideIcon[] = [
  Atom,
  Bot,
  Cpu,
  Database,
  Eye,
  Flame,
  Globe,
  Hexagon,
  InfinityIcon,
  Joystick,
  Key,
  Lightbulb,
  Magnet,
  Network,
  Orbit,
  Puzzle,
  Radar,
  Sparkles,
  Telescope,
  Umbrella,
  Video,
  Wand2,
  Zap,
  Compass,
  Feather,
  Anchor,
];

export function getAgentIcon(agentName: string | null | undefined): LucideIcon {
  const letter = (agentName || "").trim().charAt(0).toUpperCase();
  const index = letter.charCodeAt(0) - "A".charCodeAt(0);
  if (index < 0 || index >= AGENT_ICON_SET.length) {
    return Bot;
  }
  return AGENT_ICON_SET[index];
}
