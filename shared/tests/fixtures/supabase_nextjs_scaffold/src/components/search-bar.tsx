import { Suspense } from 'react'
import { SearchInput } from './search-input' // uses useSearchParams() internally

export function SearchBar() {
  return (
    <Suspense fallback={<input disabled placeholder="Search..." className="h-10 w-full rounded-md border px-3" />}>
      <SearchInput />
    </Suspense>
  )
}
