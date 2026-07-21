import { Link } from 'react-router-dom';

const icon = (name: string, className = '') => <span aria-hidden="true" className={`material-symbols-outlined ${className}`}>{name}</span>;

export default function CollectingState({ connectionId, message }: { connectionId: string; message?: string }) {
  return <div className="voyager-card p-6">
    <div className="flex items-center gap-4">
      <span className="material-symbols-outlined animate-spin text-voyager-blue">progress_activity</span>
      <div>
        <p className="font-medium text-voyager-text-primary">{message || 'Analysis is in progress…'}</p>
        <Link to={`/analysis-logs?connection=${encodeURIComponent(connectionId)}`} className="mt-1 inline-flex items-center gap-1 text-sm text-voyager-blue underline hover:text-voyager-blue-light">
          {icon('open_in_new', 'text-sm')}View analysis logs
        </Link>
      </div>
    </div>
  </div>;
}
