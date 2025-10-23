import { fetchRegions } from "../lib/api";
import Dashboard from "../components/Dashboard";

export default async function Page() {
  const data = await fetchRegions();
  return <Dashboard data={data.regions || []} />;
}
