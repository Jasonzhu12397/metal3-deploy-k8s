import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ClusterList from '../ClusterList'

// This is the exact area where two real bugs shipped together (see
// backend/tests/test_cluster_create_validation.py and
// frontend/src/lib/__tests__/api.test.ts for the other two sides of the
// same incident): a user selected the Docker (CAPD) provider, and
// because CAPD needs no flavor/image, the form correctly hides those
// fields -- but the backend validator hadn't been updated to match, so
// submission 422'd anyway. The frontend behavior itself (hiding fields
// for docker, requiring them for real cloud providers) was never
// wrong and was never covered by an automated test either. This file is
// that missing coverage, focused on the field-visibility logic itself,
// not the network request (api.clusters.create is mocked).

vi.mock('../../../lib/api', () => ({
  api: {
    clusters: {
      list: vi.fn().mockResolvedValue([]),
      create: vi.fn(),
    },
  },
  ApiError: class ApiError extends Error {},
}))

function renderClusterList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ClusterList />
    </QueryClientProvider>,
  )
}

async function openCreateModal() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /新建集群/ }))
  return user
}

describe('CreateClusterModal provider-conditional fields', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('metal3 (the default) shows neither flavor/image fields nor the cloud provider config block', async () => {
    renderClusterList()
    await openCreateModal()

    expect(screen.queryByLabelText(/控制面 Flavor/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/控制面 Image/)).not.toBeInTheDocument()
  })

  it('openstack shows the required flavor/image fields', async () => {
    renderClusterList()
    const user = await openCreateModal()

    await user.click(screen.getByText(/OpenStack（CAPO）/))

    expect(screen.getByText('控制面 Flavor / 规格')).toBeInTheDocument()
    expect(screen.getByText('控制面 Image / 模板')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('m1.large')).toBeRequired()
    expect(screen.getByPlaceholderText('ubuntu-22.04')).toBeRequired()
  })

  it('vsphere shows its own provider config fields (server/datacenter/datastore/network)', async () => {
    renderClusterList()
    const user = await openCreateModal()

    await user.click(screen.getByText(/vSphere（CAPV）/))

    expect(screen.getByText('vCenter Server')).toBeInTheDocument()
    expect(screen.getByText('Datacenter')).toBeInTheDocument()
    expect(screen.getByText('Datastore')).toBeInTheDocument()
    expect(screen.getByText('Network')).toBeInTheDocument()
  })

  it('docker (CAPD) shows neither flavor/image fields nor a provider config block -- this is the actual regression the bug fixed', async () => {
    renderClusterList()
    const user = await openCreateModal()

    await user.click(screen.getByText(/Docker（CAPD/))

    // The bug: these two fields were `required` HTML inputs shown for
    // EVERY non-metal3 provider before the fix, forcing a user to type
    // meaningless values into fields CAPD's DockerMachineTemplate
    // doesn't even have, or blocking submission if left blank.
    expect(screen.queryByText('控制面 Flavor / 规格')).not.toBeInTheDocument()
    expect(screen.queryByText('控制面 Image / 模板')).not.toBeInTheDocument()

    // Nor should any other provider's config block leak through.
    expect(screen.queryByText('Cloud 名称（clouds.yaml）')).not.toBeInTheDocument()
    expect(screen.queryByText('vCenter Server')).not.toBeInTheDocument()
    expect(screen.queryByText('StorageClass（给节点的 DataVolume 用）')).not.toBeInTheDocument()
  })

  it('switching from openstack to docker and back correctly toggles field visibility both ways', async () => {
    renderClusterList()
    const user = await openCreateModal()

    await user.click(screen.getByText(/OpenStack（CAPO）/))
    expect(screen.getByText('控制面 Flavor / 规格')).toBeInTheDocument()

    await user.click(screen.getByText(/Docker（CAPD/))
    expect(screen.queryByText('控制面 Flavor / 规格')).not.toBeInTheDocument()

    await user.click(screen.getByText(/OpenStack（CAPO）/))
    expect(screen.getByText('控制面 Flavor / 规格')).toBeInTheDocument()
  })
})
