import {
  AppstoreOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  FileTextOutlined,
  SettingOutlined,
  ShoppingOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { App as AntApp, ConfigProvider, Layout, Menu, Segmented } from 'antd'
import enUS from 'antd/es/locale/en_US'
import zhCN from 'antd/es/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import { useSaveLanguage, useSettings } from './api/hooks'
import { rememberLang, type Lang } from './i18n'
import ConfigurationDetail from './pages/ConfigurationDetail'
import Configurations from './pages/Configurations'
import Customers from './pages/Customers'
import Dashboard from './pages/Dashboard'
import ImportDetail from './pages/ImportDetail'
import Imports from './pages/Imports'
import ProductDetail from './pages/ProductDetail'
import Products from './pages/Products'
import ProformaDetail from './pages/ProformaDetail'
import QuoteBuilder from './pages/QuoteBuilder'
import Quotes from './pages/Quotes'
import Settings from './pages/Settings'

const { Sider, Header, Content } = Layout

const NAV = [
  { key: '/', icon: <DashboardOutlined />, label: 'nav.dashboard' },
  { key: '/products', icon: <ShoppingOutlined />, label: 'nav.products' },
  { key: '/imports', icon: <CloudUploadOutlined />, label: 'nav.imports' },
  { key: '/quotes', icon: <FileTextOutlined />, label: 'nav.quotes' },
  { key: '/customers', icon: <TeamOutlined />, label: 'nav.customers' },
  { key: '/configurations', icon: <AppstoreOutlined />, label: 'nav.configurations' },
  { key: '/settings', icon: <SettingOutlined />, label: 'nav.settings' },
]

function useLanguageSync() {
  const { i18n } = useTranslation()
  const settings = useSettings()
  const saveLanguage = useSaveLanguage()
  const lang = (i18n.language === 'en' ? 'en' : 'zh') as Lang

  // The server-side setting wins on load so the choice follows the data folder.
  const serverLang = settings.data?.ui_language
  useEffect(() => {
    if (serverLang && serverLang !== i18n.language) void i18n.changeLanguage(serverLang)
  }, [serverLang, i18n])

  useEffect(() => {
    dayjs.locale(lang === 'zh' ? 'zh-cn' : 'en')
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
    rememberLang(lang)
  }, [lang])

  const setLang = (next: Lang) => {
    void i18n.changeLanguage(next)
    saveLanguage.mutate(next)
  }
  return { lang, setLang }
}

export default function App() {
  const { t } = useTranslation()
  const { lang, setLang } = useLanguageSync()
  const navigate = useNavigate()
  const location = useLocation()
  const path = location.pathname.startsWith('/proformas') ? '/quotes' : location.pathname
  const selected =
    NAV.filter((n) => n.key !== '/' && path.startsWith(n.key)).map((n) => n.key)[0] ?? '/'

  return (
    <ConfigProvider
      locale={lang === 'zh' ? zhCN : enUS}
      theme={{ token: { colorPrimary: '#1f4e8c', borderRadius: 6 } }}
    >
      <AntApp>
        <Layout style={{ minHeight: '100vh' }}>
          <Sider breakpoint="lg" collapsedWidth={64} width={216}>
            <div className="qd-brand">QuoteDesk</div>
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={[selected]}
              items={NAV.map((n) => ({ key: n.key, icon: n.icon, label: t(n.label) }))}
              onClick={({ key }) => navigate(key)}
            />
          </Sider>
          <Layout>
            <Header className="qd-header">
              <span className="qd-muted">{t('app.tagline')}</span>
              <Segmented<Lang>
                value={lang}
                onChange={setLang}
                options={[
                  { label: '中文', value: 'zh' },
                  { label: 'EN', value: 'en' },
                ]}
              />
            </Header>
            <Content className="qd-content">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/products" element={<Products />} />
                <Route path="/products/:id" element={<ProductDetail />} />
                <Route path="/imports" element={<Imports />} />
                <Route path="/imports/:id" element={<ImportDetail />} />
                <Route path="/quotes" element={<Quotes />} />
                <Route path="/quotes/:id" element={<QuoteBuilder />} />
                <Route path="/proformas/:id" element={<ProformaDetail />} />
                <Route path="/customers" element={<Customers />} />
                <Route path="/configurations" element={<Configurations />} />
                <Route path="/configurations/:id" element={<ConfigurationDetail />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Content>
          </Layout>
        </Layout>
      </AntApp>
    </ConfigProvider>
  )
}
