"use client";

import { Brain, CalendarDays, CheckCircle2, Sunrise } from "lucide-react";
import { ViewKey, viewLabels } from "@/lib/views";

const views: { key: ViewKey; icon: typeof Sunrise }[] = [
  { key: "today", icon: Sunrise },
  { key: "schedule", icon: CalendarDays },
  { key: "commitments", icon: CheckCircle2 },
  { key: "decisions", icon: Brain },
];

export default function ViewNav({
  current,
  onChange,
  className = "",
  idPrefix = "view",
}: {
  current: ViewKey;
  onChange: (view: ViewKey) => void;
  className?: string;
  idPrefix?: string;
}) {
  return (
    <nav aria-label="Command center sections" className={className}>
      <div role="tablist" aria-label="Dashboard views">
        {views.map(({ key, icon: Icon }) => (
          <button
            id={`${idPrefix}-tab-${key}`}
            type="button"
            role="tab"
            aria-selected={current === key}
            aria-controls={`view-${key}`}
            className={current === key ? "selected" : ""}
            onClick={() => onChange(key)}
            key={key}
          >
            <Icon size={18} />
            <span>{viewLabels[key]}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}
