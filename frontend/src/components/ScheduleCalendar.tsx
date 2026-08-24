"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Clock3, Expand, X } from "lucide-react";
import ActionCard from "@/components/ActionCard";
import { CalendarItem, Card } from "@/lib/api";

const TIME_ZONE = "America/Los_Angeles";

function zonedParts(date: Date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  return Object.fromEntries(parts.map(part => [part.type, part.value]));
}

export function calendarKey(value: string, allDay = false) {
  if (allDay && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = zonedParts(date);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function startDay() {
  const parts = zonedParts(new Date());
  return new Date(Number(parts.year), Number(parts.month) - 1, Number(parts.day));
}

function dayKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function calendarDays(count: number) {
  const first = startDay();
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(first);
    date.setDate(first.getDate() + index);
    return date;
  });
}

function itemTime(item: CalendarItem) {
  if (item.all_day) return "All day";
  const start = new Date(item.start);
  if (Number.isNaN(start.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat("en-US", { timeZone: TIME_ZONE, hour: "numeric", minute: "2-digit" }).format(start);
}

function CalendarGrid({ items, days, onSelect }: { items: CalendarItem[]; days: number; onSelect: (item: CalendarItem) => void }) {
  const dates = useMemo(() => calendarDays(days), [days]);
  const grouped = useMemo(() => {
    const result: Record<string, CalendarItem[]> = {};
    for (const item of items) {
      const key = calendarKey(item.start, item.all_day);
      if (!key) continue;
      (result[key] ||= []).push(item);
    }
    for (const values of Object.values(result)) values.sort((a, b) => a.start.localeCompare(b.start));
    return result;
  }, [items]);

  return (
    <div className={`calendar-grid ${days > 7 ? "calendar-grid-full" : ""}`}>
      {dates.map((date, index) => {
        const key = dayKey(date);
        const dayItems = grouped[key] || [];
        return (
          <section className={`calendar-day ${index === 0 ? "today" : ""}`} key={key} aria-label={date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}>
            <header><span>{date.toLocaleDateString("en-US", { weekday: "short" })}</span><b>{date.getDate()}</b></header>
            <div className="calendar-events">
              {dayItems.map(item => (
                <button type="button" className={`calendar-event ${item.kind}`} key={item.id} onClick={() => onSelect(item)}>
                  <small>{itemTime(item)}</small><span>{item.title}</span>
                </button>
              ))}
              {!dayItems.length && <span className="calendar-clear">Clear</span>}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function ItemDetail({ item, card, onClose, onChanged }: { item: CalendarItem; card?: Card; onClose: () => void; onChanged: () => void }) {
  const dateOnly = item.all_day && /^(\d{4})-(\d{2})-(\d{2})$/.exec(item.start);
  const start = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]), 12)
    : new Date(item.start);
  const date = Number.isNaN(start.getTime()) ? item.start : new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    weekday: "long",
    month: "long",
    day: "numeric",
    ...(item.all_day ? {} : { hour: "numeric", minute: "2-digit" }),
  }).format(start);
  const end = item.end && !item.all_day ? new Date(item.end) : null;
  const endTime = end && !Number.isNaN(end.getTime())
    ? new Intl.DateTimeFormat("en-US", { timeZone: TIME_ZONE, hour: "numeric", minute: "2-digit" }).format(end)
    : "";
  return (
    <aside className={`calendar-detail ${card ? "calendar-detail-actionable" : ""}`} aria-label="Selected dated item">
      <button type="button" onClick={onClose} aria-label="Close item details"><X size={15} /></button>
      <p className="kicker">{card ? "Early action available" : item.kind === "priority" ? "Priority deadline" : "Calendar item"}</p>
      <h3>{item.title}</h3>
      <p><Clock3 size={14} />{item.all_day ? `${date} · All day` : `${date}${endTime ? ` – ${endTime}` : ""}`}</p>
      <small>Source: {item.source}</small>
      {card && (
        <div className="calendar-action">
          <div className="calendar-action-heading"><span>Prepare before this date</span><p>This future commitment needs an earlier decision or action.</p></div>
          <ActionCard card={card} onChanged={onChanged} />
        </div>
      )}
    </aside>
  );
}

export default function ScheduleCalendar({ items, cards, onChanged }: { items: CalendarItem[]; cards: Card[]; onChanged: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState<CalendarItem | null>(null);
  const selectedCard = selected?.priority_id ? cards.find(card => card.id === selected.priority_id) : undefined;

  useEffect(() => {
    if (!expanded && !selected) return;
    const close = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (selected) setSelected(null);
      else setExpanded(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [expanded, selected]);

  return (
    <section className="schedule-widget" aria-labelledby="schedule-title">
      <div className="schedule-heading">
        <div><p className="kicker">Calendar</p><h2 id="schedule-title">Next seven days</h2><p>Dated commitments and priority deadlines. Open an item for its full details.</p></div>
        <button type="button" className="calendar-expand" onClick={() => setExpanded(true)}><Expand size={15} />Open full calendar</button>
      </div>
      <div className="calendar-scroll"><CalendarGrid items={items} days={7} onSelect={setSelected} /></div>
      {!items.length && <div className="calendar-empty"><CalendarDays size={20} /><span>No dated items are available from the connected calendar.</span></div>}

      {selected && !expanded && <div className="calendar-detail-overlay" role="dialog" aria-modal="true" aria-label="Dated item details"><ItemDetail item={selected} card={selectedCard} onClose={() => setSelected(null)} onChanged={onChanged} /></div>}

      {expanded && (
        <div className="calendar-overlay" role="dialog" aria-modal="true" aria-labelledby="full-calendar-title">
          <section className="calendar-modal">
            <div className="schedule-heading full-heading">
              <div><p className="kicker">Full calendar</p><h2 id="full-calendar-title">Next 30 days</h2><p>Select any dated item to see its source and complete timing.</p></div>
              <button type="button" className="calendar-close" onClick={() => { setExpanded(false); setSelected(null); }}><X size={16} />Close</button>
            </div>
            {selected && <ItemDetail item={selected} card={selectedCard} onClose={() => setSelected(null)} onChanged={onChanged} />}
            <div className="calendar-scroll calendar-scroll-full"><CalendarGrid items={items} days={30} onSelect={setSelected} /></div>
          </section>
        </div>
      )}
    </section>
  );
}
