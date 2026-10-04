import { Card, Col, Row, Statistic } from 'antd'
import { useTranslation } from 'react-i18next'

import { useDashboard } from '../api/hooks'

/** Catalog counts shown above the product search. */
export default function CatalogStats() {
  const { t } = useTranslation()
  const dashboard = useDashboard()
  const data = dashboard.data
  const items = [
    { key: 'products', title: t('dashboard.products'), value: data?.products },
    {
      key: 'withoutPrice',
      title: t('dashboard.withoutPrice'),
      value: data?.products_without_price,
    },
    { key: 'categories', title: t('dashboard.categories'), value: data?.categories },
    { key: 'brands', title: t('dashboard.brands'), value: data?.brands },
  ]
  return (
    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
      {items.map((item) => (
        <Col xs={12} md={6} key={item.key}>
          <Card size="small" loading={dashboard.isLoading}>
            <Statistic title={item.title} value={item.value ?? 0} />
          </Card>
        </Col>
      ))}
    </Row>
  )
}
