import { Card, Col, Empty, List, Row, Statistic, Table, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { useCategories, useDashboard } from '../api/hooks'
import type { LineWarning, QuoteStatus } from '../api/quotes'
import type { Dashboard as DashboardData } from '../api/types'
import { QuoteStatusTag, WarningText } from '../components/quote/labels'
import { formatDateTime } from '../lib/datetime'
import { localName } from '../lib/i18n-helpers'
import { formatCost, formatUsd } from '../lib/money'

type Move = DashboardData['price_moves'][number]
type Alert = DashboardData['quote_alerts'][number]

export default function Dashboard() {
  const { t, i18n } = useTranslation()
  const dashboard = useDashboard()
  const categories = useCategories()
  const data = dashboard.data
  const byId = new Map((categories.data ?? []).map((c) => [c.id, c]))
  const rows = (data?.products_by_category ?? [])
    .map((r) => ({ ...r, category: byId.get(r.category_id) }))
    .sort((a, b) => b.count - a.count)
  const loading = dashboard.isLoading

  return (
    <>
      <Typography.Title level={3}>{t('nav.dashboard')}</Typography.Title>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card title={t('dashboard.lastImport')} loading={loading} style={{ height: '100%' }}>
            {data?.last_import ? (
              <>
                <Link to={`/imports/${data.last_import.id}`}>{data.last_import.filename}</Link>
                <div className="qd-muted">{formatDateTime(data.last_import.committed_at)}</div>
                <div style={{ marginTop: 8 }}>
                  {t('dashboard.importCounts', { ...data.last_import })}
                </div>
              </>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('dashboard.noImport')} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card
            title={t('dashboard.openQuotes')}
            loading={loading}
            extra={<Link to="/quotes">{t('nav.quotes')}</Link>}
          >
            <Row gutter={16}>
              <Col span={8}>
                <Statistic title={t('dashboard.openQuotes')} value={data?.open_quotes.count ?? 0} />
              </Col>
              <Col span={16}>
                <Statistic
                  title={t('dashboard.openValue')}
                  value={formatUsd(data?.open_quotes.value ?? '0')}
                />
              </Col>
            </Row>
            <List
              size="small"
              style={{ marginTop: 8 }}
              dataSource={data?.open_quotes.recent ?? []}
              locale={{ emptyText: t('dashboard.noOpenQuotes') }}
              renderItem={(q) => (
                <List.Item extra={<span className="qd-money">{formatUsd(q.grand_total)}</span>}>
                  <span>
                    <Link to={`/quotes/${q.id}`}>{q.display_no}</Link>{' '}
                    <QuoteStatusTag status={q.status as QuoteStatus} />
                    <span className="qd-muted">{q.customer_name}</span>
                  </span>
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col span={24}>
          <Card title={t('dashboard.quoteAlerts')} loading={loading}>
            <Table<Alert>
              size="small"
              rowKey={(a, i) => `${a.quote_id}-${a.line}-${a.code}-${i}`}
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              dataSource={data?.quote_alerts ?? []}
              locale={{ emptyText: t('dashboard.noAlerts') }}
              columns={[
                {
                  title: t('dashboard.quote'),
                  key: 'quote',
                  width: 220,
                  render: (_, a) => (
                    <span>
                      <Link to={`/quotes/${a.quote_id}`}>{a.display_no}</Link>
                      <div className="qd-muted">{a.customer_name}</div>
                    </span>
                  ),
                },
                { title: t('dashboard.line'), dataIndex: 'line' },
                {
                  title: t('dashboard.issue'),
                  key: 'issue',
                  render: (_, a) => <WarningText warning={a as unknown as LineWarning} />,
                },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title={t('dashboard.priceMoves')} loading={loading}>
            <Table<Move>
              size="small"
              rowKey="product_id"
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              dataSource={data?.price_moves ?? []}
              locale={{ emptyText: t('dashboard.noMoves') }}
              columns={[
                {
                  title: t('product.name'),
                  key: 'name',
                  render: (_, m) => <Link to={`/products/${m.product_id}`}>{m.name}</Link>,
                },
                {
                  title: t('dashboard.old'),
                  key: 'old',
                  align: 'right',
                  render: (_, m) => <span className="qd-money">{formatCost(m.old)}</span>,
                },
                {
                  title: t('dashboard.new'),
                  key: 'new',
                  align: 'right',
                  render: (_, m) => <span className="qd-money">{formatCost(m.new)}</span>,
                },
                {
                  title: t('dashboard.change'),
                  key: 'pct',
                  align: 'right',
                  render: (_, m) => (
                    <span style={{ color: m.pct.startsWith('-') ? '#389e0d' : '#cf1322' }}>
                      {m.pct.startsWith('-') ? '' : '+'}
                      {m.pct}%
                    </span>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={t('dashboard.oldPrices', { days: data?.old_prices.days ?? 30 })}
            loading={loading}
          >
            {data && data.old_prices.count > 0 ? (
              <>
                <Statistic
                  value={t('dashboard.oldPricesCount', { count: data.old_prices.count })}
                />
                <List
                  size="small"
                  dataSource={data.old_prices.oldest}
                  renderItem={(p) => (
                    <List.Item extra={<span className="qd-muted">{p.price_date}</span>}>
                      <Link to={`/products/${p.product_id}`}>{p.name}</Link>
                    </List.Item>
                  )}
                />
              </>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('dashboard.noOldPrices')}
              />
            )}
          </Card>
        </Col>

        <Col span={24}>
          <Card title={t('dashboard.byCategory')} loading={loading}>
            <Table
              size="small"
              rowKey="category_id"
              pagination={false}
              dataSource={rows}
              locale={{ emptyText: t('dashboard.empty') }}
              columns={[
                {
                  title: t('product.category'),
                  render: (_, r) => (
                    <Link to={`/products?category=${r.category_id}`}>
                      {localName(r.category, i18n.language)}
                    </Link>
                  ),
                },
                { title: t('dashboard.count'), dataIndex: 'count', align: 'right' },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </>
  )
}
