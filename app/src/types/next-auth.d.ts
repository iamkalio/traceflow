import { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      /** GitHub numeric account ID stored as string — used as tenant_id to scope traces/evals. */
      tenantId: string | null;
    } & DefaultSession["user"];
  }
}
