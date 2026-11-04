import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

const NAV = [
  { to: '/', label: '대시보드', end: true },
  { to: '/meetings', label: '회의 목록', end: false },
  { to: '/meetings/new', label: '새 회의', end: true },
  { to: '/settings', label: '설정', end: true },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const { pathname } = useLocation()
  // '/meetings/new' 에서 '회의 목록'이 함께 활성화되지 않도록 처리
  const active = (to: string, end: boolean) =>
    end ? pathname === to : pathname.startsWith(to) && pathname !== '/meetings/new'
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-gray-200 bg-white md:fixed md:inset-y-0 md:w-56 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-4 py-3 md:block md:py-5">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-600 text-sm font-bold text-white">M</div>
            <span className="font-semibold">Meeting Mate</span>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={() => `whitespace-nowrap rounded-md px-3 py-1.5 text-sm ${active(n.to, n.end) ? 'bg-gray-100 font-medium text-gray-900' : 'text-gray-600 hover:bg-gray-50'}`}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden border-t px-4 py-3 md:absolute md:bottom-0 md:block md:w-full">
          <p className="truncate text-sm font-medium">{user?.name}</p>
          <p className="truncate text-xs text-gray-500">{user?.email}</p>
          <button className="mt-2 text-xs text-gray-500 hover:text-gray-800" onClick={() => { logout(); nav('/login') }}>로그아웃</button>
        </div>
      </aside>
      <main className="flex-1 md:ml-56">
        <div className="mx-auto max-w-6xl px-4 py-6 md:px-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
