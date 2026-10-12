import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { ApiError } from '../api/errors'
import { SessionProvider } from '../api/session'
import { makeRouter } from './routes'

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: 5_000, retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2 } },
  })
}

export function App({ client = makeQueryClient(), router = makeRouter() }: { client?: QueryClient; router?: ReturnType<typeof makeRouter> }) {
  return (
    <QueryClientProvider client={client}>
      <SessionProvider><RouterProvider router={router} /></SessionProvider>
    </QueryClientProvider>
  )
}
