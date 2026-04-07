import { defineConfig } from '@prisma/config'
import * as dotenv from 'dotenv'
dotenv.config()

export default defineConfig({
  earlyAccess: true,
  datasource: {
    url: process.env.DATABASE_URL,
  },
  migrations: {
    url: process.env.DATABASE_URL,
  },
})
