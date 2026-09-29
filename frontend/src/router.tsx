import { Navigate, createBrowserRouter } from 'react-router-dom'
import { ProfilePage } from './pages/ProfilePage'
import { RegisterPage } from './pages/RegisterPage'

const hasToken = () => Boolean(sessionStorage.getItem('qa_lab_access_token'))
function RegisterRoute() { return hasToken() ? <Navigate to="/profile" replace /> : <RegisterPage /> }
function UnknownRoute() { return <Navigate to={hasToken() ? '/profile' : '/register'} replace /> }
export const router = createBrowserRouter([
  { path: '/register', element: <RegisterRoute /> },
  { path: '/profile', element: <ProfilePage /> },
  { path: '*', element: <UnknownRoute /> },
])
