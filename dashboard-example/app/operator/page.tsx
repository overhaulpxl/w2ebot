import { getDashboardSession } from "@/lib/dashboardAuth";
import { redirect } from "next/navigation";
import { OperatorUserManagement } from "@/components/OperatorUserManagement";

export default async function Page() {
  const session = await getDashboardSession("OPERATOR_WRITE");
  if (!session) redirect("/api/auth/login");
  
  return (
    <section className="card card-pad">
      <h2>Manajemen User & Keuangan</h2>
      <OperatorUserManagement />
    </section>
  );
}