import { PrismaAdapter } from "@auth/prisma-adapter";
import { type NextAuthOptions } from "next-auth";
import GithubProvider from "next-auth/providers/github";
import { prisma } from "@/lib/prisma";

export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma) as any,
  session: {
    strategy: "jwt",
  },
  providers: [
    GithubProvider({
      clientId: process.env.GITHUB_ID ?? "",
      clientSecret: process.env.GITHUB_SECRET ?? "",
    }),
  ],
  callbacks: {
    jwt: async ({ token, user, account }) => {
      // 'user' and 'account' are only present on the initial sign-in.
      if (user) {
        token.sub = user.id;
      }
      if (account?.provider === "github" && account.providerAccountId) {
        token.tenantId = account.providerAccountId;
      }
      return token;
    },

    session: async ({ session, token }) => {
      if (session.user) {
        session.user.id = token.sub as string;
        session.user.tenantId = (token.tenantId as string | null) ?? null;
      }
      return session;
    },
  },
  pages: {
    signIn: "/auth/signin",
  },
};
