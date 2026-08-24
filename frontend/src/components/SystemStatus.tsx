const systems = [
  { key: "eli_agent", label: "Eli" },
  { key: "composio", label: "Connected apps" },
  { key: "anthropic", label: "Priority engine" },
] as const;

export default function SystemStatus({ integrations }: { integrations: Record<string, boolean | string> }) {
  return (
    <div className="systems">
      <p>Systems</p>
      {systems.map(system => {
        const connected = Boolean(integrations[system.key]);
        return (
          <div key={system.key}>
            <i className={connected ? "online" : "offline"} />
            <span>{system.label}</span>
            <small>{connected ? "Connected" : "Unavailable"}</small>
          </div>
        );
      })}
    </div>
  );
}
