import { PrismaAdapter } from "@auth/prisma-adapter";
import { type NextAuthOptions } from "next-auth";
import GithubProvider from "next-auth/providers/github";
import { prisma } from "@/lib/prisma";

export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma) as any,
  providers: [
    GithubProvider({
      clientId: process.env.GITHUB_ID || "",
      clientSecret: process.env.GITHUB_SECRET || "",
    }),
  ],
  callbacks: {
    /**
     * After a successful sign-in, persist the GitHub numeric account ID
     * as `tenantId` on the User row so traces/evals can be scoped to it.
     */
    signIn: async ({ user, account }) => {
      if (account?.provider === "github" && account.providerAccountId) {
        await prisma.user.update({
          where: { id: user.id },
          data: { tenantId: account.providerAccountId },
        });
      }
      return true;
    },

    /**
     * Attach id and tenantId to the session so client components can read them.
     */
    session: async ({ session, user }) => {
      if (session.user) {
        session.user.id = user.id;
        // user is the raw DB row from PrismaAdapter — tenantId lives there
        session.user.tenantId = (user as { tenantId?: string | null }).tenantId ?? null;
      }
      return session;
    },
  },
  pages: {
    signIn: "/auth/signin",
  },
};
