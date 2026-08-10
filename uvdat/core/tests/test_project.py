from __future__ import annotations

from typing import TYPE_CHECKING

import faker
import pytest
from pytest_lazy_fixtures import lf

if TYPE_CHECKING:
    from uvdat.core.models.project import Project


@pytest.mark.django_db
def test_project_set_owner(project, user):
    owner = project.owner()
    assert owner.id != user.id

    project.set_owner(user)
    assert project.owner().id == user.id


@pytest.mark.django_db
def test_project_set_followers_collaborators(project, user_factory):
    def sort_func(user):
        return user.id

    users = sorted([user_factory() for _ in range(5)], key=sort_func)
    assert not project.followers()
    assert not project.collaborators()

    project.set_followers(users)

    # Check that users added as collaborators were automatically removed from followers
    project.set_collaborators(users)
    assert not project.followers()
    assert sorted(project.collaborators(), key=sort_func) == users

    # Check that users added as followers were automatically removed from collaborators
    project.set_followers(users)
    assert not project.collaborators()
    assert sorted(project.followers(), key=sort_func) == users


@pytest.mark.parametrize(
    ("client", "anon"),
    [(lf("api_client"), True), (lf("authenticated_api_client"), False)],
)
@pytest.mark.django_db
def test_rest_list_projects(client, anon, user, user_factory, project_factory):
    project = project_factory()
    project.set_owner(user)
    demo = project_factory(allow_unauthenticated=True)
    demo.set_owner(user_factory())  # set owner to a different user
    resp = client.get("/api/v1/projects/")
    assert resp.status_code == 200
    results = resp.json().get("results")
    if anon:
        assert len(results) == 1
        assert results[0].get("name") == demo.name
    else:
        assert len(results) == 2
        assert {result.get("name") for result in results} == {project.name, demo.name}


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 201)],
)
@pytest.mark.django_db
def test_rest_project_create_no_datasets(client, expected_status):
    fake = faker.Faker()
    resp = client.post(
        "/api/v1/projects/",
        data={
            "name": fake.name(),
            "default_map_zoom": fake.pyfloat(min_value=0, max_value=22),
            "default_map_center": [fake.latitude(), fake.longitude()],
        },
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 201)],
)
@pytest.mark.django_db
def test_rest_project_create_with_datasets(client, expected_status, dataset_factory):
    fake = faker.Faker()

    datasets = [dataset_factory().id for _ in range(3)]
    resp = client.post(
        "/api/v1/projects/",
        data={
            "name": fake.name(),
            "default_map_zoom": fake.pyfloat(min_value=0, max_value=22),
            "default_map_center": [fake.latitude(), fake.longitude()],
            "datasets": datasets,
        },
    )

    assert resp.status_code == expected_status


@pytest.mark.django_db
def test_rest_project_retrieve(authenticated_api_client, user, project: Project):
    # Not found because user is not added to project
    resp = authenticated_api_client.get(f"/api/v1/projects/{project.id}/")
    assert resp.status_code == 404

    project.set_followers([user])
    resp = authenticated_api_client.get(f"/api/v1/projects/{project.id}/")

    assert resp.json()["owner"]["id"]
    assert not resp.json()["collaborators"]

    followers = resp.json()["followers"]
    assert len(followers) == 1
    assert followers[0]["id"] == user.id

    assert resp.json()["item_counts"] == {
        "datasets": 0,
        "charts": 0,
        "analyses": 0,
    }


@pytest.mark.django_db
def test_rest_project_set_permissions_not_allowed(authenticated_api_client, user, project: Project):
    resp = authenticated_api_client.put(
        f"/api/v1/projects/{project.id}/permissions/",
        {
            "owner_id": user.id,
            "collaborator_ids": [],
            "follower_ids": [],
        },
    )
    # 404 because user is not added to the project at all
    assert resp.status_code == 404

    project.set_followers([user])
    resp = authenticated_api_client.put(
        f"/api/v1/projects/{project.id}/permissions/",
        {
            "owner_id": user.id,
            "collaborator_ids": [],
            "follower_ids": [],
        },
    )
    # User is added, but without sufficient perms, so 403 is returned
    assert resp.status_code == 403


@pytest.mark.django_db
def test_rest_project_set_permissions_change_owner_collaborator(
    authenticated_api_client, user, project: Project
):
    project.set_collaborators([user])
    resp = authenticated_api_client.put(
        f"/api/v1/projects/{project.id}/permissions/",
        {
            "owner_id": user.id,
            "collaborator_ids": [],
            "follower_ids": [],
        },
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_rest_project_set_permissions_change_owner(api_client, user, project: Project):
    owner = project.owner()
    api_client.force_authenticate(user=owner)
    resp = api_client.put(
        f"/api/v1/projects/{project.id}/permissions/",
        {
            "owner_id": user.id,
            "collaborator_ids": [owner.id],
            "follower_ids": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["owner"]["id"] == user.id
    assert resp.json()["collaborators"][0]["id"] == owner.id


@pytest.mark.django_db
def test_rest_project_delete(authenticated_api_client, user, project: Project):
    resp = authenticated_api_client.delete(f"/api/v1/projects/{project.id}/")
    assert resp.status_code == 404

    project.set_followers([user])
    resp = authenticated_api_client.delete(f"/api/v1/projects/{project.id}/")
    assert resp.status_code == 403

    project.set_collaborators([user])
    resp = authenticated_api_client.delete(f"/api/v1/projects/{project.id}/")
    assert resp.status_code == 403

    project.set_owner(user)
    resp = authenticated_api_client.delete(f"/api/v1/projects/{project.id}/")
    assert resp.status_code == 204


@pytest.mark.parametrize("superuser", [True, False])
@pytest.mark.django_db
def test_rest_update_allow_unauthenticated(authenticated_api_client, user, superuser, project):
    if superuser:
        user.is_superuser = True
        user.save()
    else:
        project.set_owner(user)

    resp = authenticated_api_client.patch(
        f"/api/v1/projects/{project.id}/",
        {"allow_unauthenticated": True},
    )
    assert resp.status_code == (200 if superuser else 400)
    project.refresh_from_db()
    assert project.allow_unauthenticated == superuser
