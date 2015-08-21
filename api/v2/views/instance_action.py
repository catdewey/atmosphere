from django.shortcuts import Http404

from rest_framework import viewsets
from rest_framework import status
from rest_framework.response import Response

from api.v2.serializers import InstanceActionSerializer
from core.models import Instance
from service.action import create_action_manager

action_manager = create_action_manager()


class InstanceActionViewSet(viewsets.ViewSet):

    def create(self, request):
        """
        Runs an instance action
        """
        serializer = InstanceActionSerializer(data=self.request.data,
                                              actions=action_manager.actions)
        serializer.is_valid(raise_exception=True)
        response = self.perform_create(serializer)

        return Response(data=response, status=status.HTTP_204_NO_CONTENT)

    def list(self, request):
        """
        List of available actions to perform on an instance
        """
        return Response(data=action_manager.get_catalog_info())

    def perform_create(self, serializer):
        """
        Executes the instance action
        """
        action = serializer.validated_data.get("action")
        data = serializer.validated_data.get("data", {})
        action.execute(data)