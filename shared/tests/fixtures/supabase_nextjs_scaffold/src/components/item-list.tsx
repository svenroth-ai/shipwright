'use client'
import { useState } from 'react'

export function ItemList({ initialItems }: { initialItems: Item[] }) {
  const [items, setItems] = useState(initialItems)

  return (
    <>
      <CreateDialog onSuccess={(created) => setItems((prev) => [...prev, created])} />
      {items.map((item) => (
        <ItemCard
          key={item.id}
          item={item}
          onUpdate={(updated) => setItems((prev) => prev.map((i) => i.id === updated.id ? updated : i))}
          onDelete={(id) => setItems((prev) => prev.filter((i) => i.id !== id))}
        />
      ))}
    </>
  )
}
