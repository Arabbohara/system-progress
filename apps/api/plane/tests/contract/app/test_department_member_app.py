# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Department membership grants access to every project of the department.

Joining a department creates ProjectMember rows tagged with ``source_department``;
leaving removes only those rows, never memberships that were added manually.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    Department,
    DepartmentMember,
    Project,
    ProjectMember,
    User,
    WorkspaceMember,
)


def _make_user(email: str) -> User:
    local_part = email.split("@")[0]
    user = User.objects.create(email=email, username=local_part, first_name=local_part)
    user.set_password("test-password")
    user.save()
    return user


def _client(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_project(workspace, owner, name, identifier, department=None, network=2) -> Project:
    project = Project.objects.create(
        name=name,
        identifier=identifier,
        workspace=workspace,
        created_by=owner,
        department=department,
        network=network,
    )
    ProjectMember.objects.create(workspace=workspace, project=project, member=owner, role=20, is_active=True)
    return project


def _membership(project, user):
    return ProjectMember.objects.filter(project=project, member=user).first()


@pytest.fixture
def department(db, workspace):
    return Department.objects.create(workspace=workspace, name="Sales")


@pytest.fixture
def other_department(db, workspace):
    return Department.objects.create(workspace=workspace, name="Logistics")


@pytest.fixture
def member_user(db, workspace):
    user = _make_user("dept-member@vegecoop.co.jp")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15, is_active=True)
    return user


@pytest.fixture
def guest_user(db, workspace):
    user = _make_user("dept-guest@vegecoop.co.jp")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=5, is_active=True)
    return user


@pytest.mark.contract
@pytest.mark.django_db
class TestDepartmentMembership:
    def test_admin_adds_member_to_all_department_projects(
        self, workspace, create_user, department, other_department, member_user
    ):
        p1 = _make_project(workspace, create_user, "Sales A", "SLA", department)
        p2 = _make_project(workspace, create_user, "Sales B", "SLB", department)
        outside = _make_project(workspace, create_user, "Logistics", "LOG", other_department)

        response = _client(create_user).post(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/",
            {"members": [{"member_id": str(member_user.id), "role": 20}]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        for project in (p1, p2):
            membership = _membership(project, member_user)
            assert membership.is_active is True
            assert membership.role == 20
            assert membership.source_department_id == department.id
        assert _membership(outside, member_user) is None

    def test_non_admin_cannot_add_members(self, workspace, department, member_user, guest_user):
        response = _client(member_user).post(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/",
            {"members": [{"member_id": str(guest_user.id), "role": 5}]},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not DepartmentMember.objects.filter(member=guest_user).exists()

    def test_self_join_grants_member_role(self, workspace, create_user, department, member_user):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)

        response = _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        assert response.status_code == status.HTTP_201_CREATED
        membership = _membership(project, member_user)
        assert membership.is_active is True
        assert membership.role == 15

    def test_guest_cannot_self_join(self, workspace, department, guest_user):
        response = _client(guest_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_guest_added_by_admin_stays_guest(self, workspace, create_user, department, guest_user):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)

        _client(create_user).post(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/",
            {"members": [{"member_id": str(guest_user.id), "role": 20}]},
            format="json",
        )

        assert _membership(project, guest_user).role == 5

    def test_leave_removes_only_department_access(self, workspace, create_user, department, member_user):
        dept_project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        manual_project = _make_project(workspace, create_user, "Sales B", "SLB", department)
        ProjectMember.objects.create(
            workspace=workspace, project=manual_project, member=member_user, role=15, is_active=True
        )
        client = _client(member_user)
        client.post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        response = client.delete(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert _membership(dept_project, member_user).is_active is False
        manual = _membership(manual_project, member_user)
        assert manual.is_active is True
        assert manual.source_department_id is None
        assert not DepartmentMember.objects.filter(member=member_user).exists()

    def test_member_cannot_remove_someone_else(self, workspace, create_user, department, member_user, guest_user):
        admin_client = _client(create_user)
        admin_client.post(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/",
            {"members": [{"member_id": str(guest_user.id), "role": 5}]},
            format="json",
        )
        department_member = DepartmentMember.objects.get(member=guest_user)

        response = _client(member_user).delete(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/{department_member.id}/"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert DepartmentMember.objects.filter(pk=department_member.pk).exists()

    def test_role_update_applies_to_department_projects(self, workspace, create_user, department, member_user):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        department_member = DepartmentMember.objects.create(
            workspace=workspace, department=department, member=member_user, role=15
        )
        ProjectMember.objects.create(
            workspace=workspace, project=project, member=member_user, role=15, source_department=department
        )

        response = _client(create_user).patch(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/{department_member.id}/",
            {"role": 5},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert _membership(project, member_user).role == 5

    def test_sole_admin_keeps_access_after_leaving(self, workspace, create_user, department, member_user):
        project = Project.objects.create(
            name="Orphan", identifier="ORP", workspace=workspace, created_by=create_user, department=department
        )
        DepartmentMember.objects.create(workspace=workspace, department=department, member=member_user, role=20)
        ProjectMember.objects.create(
            workspace=workspace, project=project, member=member_user, role=20, source_department=department
        )

        _client(member_user).delete(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        membership = _membership(project, member_user)
        assert membership.is_active is True
        assert membership.source_department_id is None

    def test_moving_project_between_departments(
        self, workspace, create_user, department, other_department, member_user
    ):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")
        assert _membership(project, member_user).is_active is True

        response = _client(create_user).patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/",
            {"department": str(other_department.id)},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert _membership(project, member_user).is_active is False

        _client(create_user).patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/",
            {"department": str(department.id)},
            format="json",
        )
        membership = _membership(project, member_user)
        assert membership.is_active is True
        assert membership.source_department_id == department.id

    def test_new_project_in_department_includes_members(self, workspace, create_user, department, member_user):
        DepartmentMember.objects.create(workspace=workspace, department=department, member=member_user, role=15)

        response = _client(create_user).post(
            f"/api/workspaces/{workspace.slug}/projects/",
            {"name": "New Sales", "identifier": "NSL", "department": str(department.id)},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        membership = ProjectMember.objects.get(project_id=response.data["id"], member=member_user)
        assert membership.is_active is True
        assert membership.source_department_id == department.id

    def test_manual_add_converts_department_membership(self, workspace, create_user, department, member_user):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        client = _client(member_user)
        client.post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        _client(create_user).post(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/",
            {"members": [{"member_id": str(member_user.id), "role": 15}]},
            format="json",
        )
        client.delete(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        assert _membership(project, member_user).is_active is True

    def test_deleting_department_keeps_project_access(self, workspace, create_user, department, member_user):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        response = _client(create_user).delete(f"/api/workspaces/{workspace.slug}/departments/{department.id}/")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        membership = _membership(project, member_user)
        assert membership.is_active is True
        assert membership.source_department_id is None

    def test_list_department_members(self, workspace, create_user, department, member_user):
        DepartmentMember.objects.create(workspace=workspace, department=department, member=member_user, role=15)

        response = _client(member_user).get(f"/api/workspaces/{workspace.slug}/departments/members/")

        assert response.status_code == status.HTTP_200_OK
        assert [(row["department_id"], row["member_id"]) for row in response.data] == [
            (department.id, member_user.id)
        ]

    def test_self_join_skips_secret_projects(self, workspace, create_user, department, member_user):
        public = _make_project(workspace, create_user, "Sales Public", "SLP", department)
        secret = _make_project(workspace, create_user, "Sales Secret", "SLS", department, network=0)

        _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        assert _membership(public, member_user).is_active is True
        assert _membership(secret, member_user) is None
        assert DepartmentMember.objects.get(member=member_user).full_access is False

    def test_admin_added_member_gets_secret_projects(self, workspace, create_user, department, member_user):
        secret = _make_project(workspace, create_user, "Sales Secret", "SLS", department, network=0)

        _client(create_user).post(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/",
            {"members": [{"member_id": str(member_user.id), "role": 15}]},
            format="json",
        )

        assert _membership(secret, member_user).is_active is True

    def test_admin_can_toggle_full_access(self, workspace, create_user, department, member_user):
        secret = _make_project(workspace, create_user, "Sales Secret", "SLS", department, network=0)
        _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")
        department_member = DepartmentMember.objects.get(member=member_user)
        url = f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/{department_member.id}/"
        admin_client = _client(create_user)

        response = admin_client.patch(url, {"full_access": True}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert _membership(secret, member_user).is_active is True

        admin_client.patch(url, {"full_access": False}, format="json")
        assert _membership(secret, member_user).is_active is False

        admin_client.patch(url, {"full_access": True}, format="json")
        assert _membership(secret, member_user).is_active is True

    def test_project_turning_secret_removes_self_joined_members(
        self, workspace, create_user, department, member_user, guest_user
    ):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")
        _client(create_user).post(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/",
            {"members": [{"member_id": str(guest_user.id), "role": 5}]},
            format="json",
        )

        response = _client(create_user).patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/", {"network": 0}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert _membership(project, member_user).is_active is False
        assert _membership(project, guest_user).is_active is True

        _client(create_user).patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/", {"network": 2}, format="json"
        )
        assert _membership(project, member_user).is_active is True

    def test_workspace_role_change_updates_department_projects(
        self, workspace, create_user, department, member_user
    ):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")
        assert _membership(project, member_user).role == 15
        workspace_member = WorkspaceMember.objects.get(workspace=workspace, member=member_user)

        response = _client(create_user).patch(
            f"/api/workspaces/{workspace.slug}/members/{workspace_member.id}/", {"role": 20}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert _membership(project, member_user).role == 20

    def test_manual_removal_survives_role_change(self, workspace, create_user, department, member_user):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        department_member = DepartmentMember.objects.create(
            workspace=workspace, department=department, member=member_user, role=15
        )
        ProjectMember.objects.create(
            workspace=workspace,
            project=project,
            member=member_user,
            role=15,
            source_department=department,
            is_active=False,
        )

        _client(create_user).patch(
            f"/api/workspaces/{workspace.slug}/departments/{department.id}/members/{department_member.id}/",
            {"role": 5},
            format="json",
        )

        assert _membership(project, member_user).is_active is False

    def test_project_members_list_shows_source_department(self, workspace, create_user, department, member_user):
        project = _make_project(workspace, create_user, "Sales A", "SLA", department)
        _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        response = _client(create_user).get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/")

        assert response.status_code == status.HTTP_200_OK
        sources = {str(row["member"]): row["source_department"] for row in response.data}
        assert sources[str(member_user.id)] == department.id
        assert sources[str(create_user.id)] is None


@pytest.mark.contract
@pytest.mark.django_db
class TestDepartmentBulkJoin:
    def test_join_all_departments(self, workspace, create_user, department, other_department, member_user):
        sales = _make_project(workspace, create_user, "Sales A", "SLA", department)
        logistics = _make_project(workspace, create_user, "Logistics", "LOG", other_department)

        response = _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/join/", {}, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2
        for project, source in ((sales, department), (logistics, other_department)):
            membership = _membership(project, member_user)
            assert membership.is_active is True
            assert membership.role == 15
            assert membership.source_department_id == source.id

    def test_join_all_skips_departments_already_joined(self, workspace, department, other_department, member_user):
        client = _client(member_user)
        client.post(f"/api/workspaces/{workspace.slug}/departments/{department.id}/join/")

        response = client.post(f"/api/workspaces/{workspace.slug}/departments/join/", {}, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert [row["department_id"] for row in response.data] == [other_department.id]
        assert DepartmentMember.objects.filter(member=member_user).count() == 2

    def test_join_selected_departments(self, workspace, department, other_department, member_user):
        response = _client(member_user).post(
            f"/api/workspaces/{workspace.slug}/departments/join/",
            {"department_ids": [str(department.id)]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert list(DepartmentMember.objects.filter(member=member_user).values_list("department_id", flat=True)) == [
            department.id
        ]

    def test_join_all_skips_secret_projects(self, workspace, create_user, department, member_user):
        secret = _make_project(workspace, create_user, "Sales Secret", "SLS", department, network=0)

        _client(member_user).post(f"/api/workspaces/{workspace.slug}/departments/join/", {}, format="json")

        assert _membership(secret, member_user) is None

    def test_guest_cannot_join_all(self, workspace, department, guest_user):
        response = _client(guest_user).post(f"/api/workspaces/{workspace.slug}/departments/join/", {}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not DepartmentMember.objects.filter(member=guest_user).exists()
