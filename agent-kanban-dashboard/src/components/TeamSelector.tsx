import type { Team } from '../types/kanban';

interface Props {
  teams: Team[];
  selectedId: string | null;
  onChange: (id: string) => void;
}

export default function TeamSelector({ teams, selectedId, onChange }: Props) {
  return (
    <select
      value={selectedId || ''}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-1.5 text-sm border border-gray-300 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
    >
      {teams.map((t) => (
        <option key={t.id} value={t.id}>
          {t.name}
        </option>
      ))}
    </select>
  );
}
