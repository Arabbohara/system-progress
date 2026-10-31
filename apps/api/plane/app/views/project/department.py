# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import transaction
from django.db.models import Count, Q

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import DepartmentMemberSerializer, DepartmentSerializer
from plane.app.views.base import BaseAPIView, BaseViewSet
from plane.db.models import Department, DepartmentMember, ProjectMember, Workspace, WorkspaceMember
from plane.utils.department_access import revoke_department_member_access, sync_department_member_access

DEPARTMENT_ROLES = [ROLE.ADMIN.value, ROLE.MEMBER.value, ROLE.GUEST.value]


class DepartmentViewSet(BaseViewSet):
    serializer_class = DepartmentSerializer
    model = Department

    def get_queryset(self):
        return Department.objects.filter(workspace__slug=self.kwargs.get("slug")).annotate(
            project_count=Count(
                "department_projects",
                filter=Q(
                    department_projects__deleted_at__isnull=True,
                    department_projects__archived_at__isnull=True,
                ),
                distinct=True,
            )
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def list(self, request, slug):
        serializer = DepartmentSerializer(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def create(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        serializer = DepartmentSerializer(data=request.data, context={"workspace_id": workspace.id})
        serializer.is_valid(raise_exception=True)
        serializer.save(workspace_id=workspace.id)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def partial_update(self, request, slug, pk=None):
        workspace = Workspace.objects.get(slug=slug)
        department = self.get_queryset().get(pk=pk)
        serializer = DepartmentSerializer(
            department,
            data=request.data,
            partial=True,
            context={"workspace_id": workspace.id},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def destroy(self, request, slug, pk=None):
        department = self.get_queryset().get(pk=pk)
        with transaction.atomic():
            # Members keep the project access they had; it becomes a manual membership
            ProjectMember.objects.filter(source_department=department).update(source_department=None)
            DepartmentMember.objects.filter(department=department).delete()
            department.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DepartmentMemberViewSet(BaseViewSet):
    serializer_class = DepartmentMemberSerializer
    model = DepartmentMember

    def get_queryset(self):
        return DepartmentMember.objects.filter(
            workspace__slug=self.kwargs.get("slug"),
            department__deleted_at__isnull=True,
            member__member_workspace__workspace__slug=self.kwargs.get("slug"),
            member__member_workspace__is_active=True,
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def list(self, request, slug):
        serializer = DepartmentMemberSerializer(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def create(self, request, slug, department_id):
        department = Department.objects.get(pk=department_id, workspace__slug=slug)
        members = request.data.get("members", [])
        if not isinstance(members, list) or not members:
            return Response({"error": "At least one member is required"}, status=status.HTTP_400_BAD_REQUEST)

        member_roles = {}
        for member in members:
            role = member.get("role", ROLE.MEMBER.value)
            if role not in DEPARTMENT_ROLES:
                return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
            member_roles[str(member.get("member_id"))] = role

        workspace_member_ids = {
            str(member_id)
            for member_id in WorkspaceMember.objects.filter(
                workspace__slug=slug, member_id__in=member_roles.keys(), is_active=True
            ).values_list("member_id", flat=True)
        }
        if workspace_member_ids != set(member_roles.keys()):
            return Response(
                {"error": "All members must be active members of the workspace"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        department_members = []
        with transaction.atomic():
            existing = {
                str(department_member.member_id): department_member
                for department_member in DepartmentMember.objects.filter(
                    department=department, member_id__in=member_roles.keys()
                )
            }
            for member_id, role in member_roles.items():
                # Members an admin adds get every project of the department, including secret ones
                department_member = existing.get(member_id)
                if department_member is None:
                    department_member = DepartmentMember.objects.create(
                        workspace_id=department.workspace_id,
                        department=department,
                        member_id=member_id,
                        role=role,
                        full_access=True,
                    )
                else:
                    department_member.role = role
                    department_member.full_access = True
                    department_member.save(update_fields=["role", "full_access", "updated_at"])
                sync_department_member_access(department_member)
                department_members.append(department_member)

        serializer = DepartmentMemberSerializer(department_members, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def partial_update(self, request, slug, department_id, pk):
        department_member = self.get_queryset().get(pk=pk, department_id=department_id)
        update_fields = []
        if "role" in request.data:
            if request.data["role"] not in DEPARTMENT_ROLES:
                return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
            department_member.role = request.data["role"]
            update_fields.append("role")
        if "full_access" in request.data:
            if not isinstance(request.data["full_access"], bool):
                return Response({"error": "`full_access` must be a boolean"}, status=status.HTTP_400_BAD_REQUEST)
            department_member.full_access = request.data["full_access"]
            update_fields.append("full_access")
        if not update_fields:
            return Response({"error": "Nothing to update"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            department_member.save(update_fields=[*update_fields, "updated_at"])
            # Granting full access restores project access; a plain role change leaves manual removals alone
            sync_department_member_access(
                department_member,
                reactivate="full_access" in update_fields and department_member.full_access,
            )

        serializer = DepartmentMemberSerializer(department_member)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def destroy(self, request, slug, department_id, pk):
        department_member = self.get_queryset().get(pk=pk, department_id=department_id)

        is_workspace_admin = WorkspaceMember.objects.filter(
            workspace__slug=slug, member=request.user, role=ROLE.ADMIN.value, is_active=True
        ).exists()
        if not is_workspace_admin and department_member.member_id != request.user.id:
            return Response(
                {"error": "You don't have the required permissions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            revoke_department_member_access(department_member.department_id, department_member.member_id)
            department_member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DepartmentJoinEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def post(self, request, slug, department_id):
        department = Department.objects.get(pk=department_id, workspace__slug=slug)

        department_member = DepartmentMember.objects.filter(department=department, member=request.user).first()
        if department_member is not None:
            return Response({"error": "You are already a member of this department"}, status=status.HTTP_409_CONFLICT)

        with transaction.atomic():
            # Joining yourself only grants the department's public projects; an admin can grant the rest
            department_member = DepartmentMember.objects.create(
                workspace_id=department.workspace_id,
                department=department,
                member=request.user,
                role=ROLE.MEMBER.value,
                full_access=False,
            )
            sync_department_member_access(department_member)

        serializer = DepartmentMemberSerializer(department_member)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def delete(self, request, slug, department_id):
        department_member = DepartmentMember.objects.get(
            department_id=department_id, department__workspace__slug=slug, member=request.user
        )
        with transaction.atomic():
            revoke_department_member_access(department_member.department_id, department_member.member_id)
            department_member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DepartmentBulkJoinEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def post(self, request, slug):
        """Join several departments at once; without `department_ids`, join every department."""
        departments = Department.objects.filter(workspace__slug=slug)
        department_ids = request.data.get("department_ids")
        if department_ids is not None:
            if not isinstance(department_ids, list):
                return Response({"error": "`department_ids` must be a list"}, status=status.HTTP_400_BAD_REQUEST)
            departments = departments.filter(pk__in=department_ids)

        joined_department_ids = DepartmentMember.objects.filter(workspace__slug=slug, member=request.user).values_list(
            "department_id", flat=True
        )
        departments = departments.exclude(pk__in=joined_department_ids)

        department_members = []
        with transaction.atomic():
            for department in departments:
                # Same rule as joining one department: only its public projects are granted
                department_member = DepartmentMember.objects.create(
                    workspace_id=department.workspace_id,
                    department=department,
                    member=request.user,
                    role=ROLE.MEMBER.value,
                    full_access=False,
                )
                sync_department_member_access(department_member)
                department_members.append(department_member)

        serializer = DepartmentMemberSerializer(department_members, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
