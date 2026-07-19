import { useSearchParams } from 'react-router-dom';
import MidPanel from '../components/MidPanel';
import WikiContent from '../components/WikiContent';

export default function WikiPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedPage = searchParams.get('path') || null;

  const handleSelectPage = (path: string) => {
    setSearchParams({ path });
  };

  return (
    <div className="flex flex-1 min-h-0">
      <MidPanel onSelectPage={handleSelectPage} />
      <WikiContent
        path={selectedPage}
        onBack={() => setSearchParams({})}
        onNavigate={handleSelectPage}
      />
    </div>
  );
}
