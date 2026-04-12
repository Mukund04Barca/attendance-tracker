from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_datetime
from .models import AttendanceRecord

from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']

class AttendanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = ['id', 'date', 'check_in', 'check_out', 'is_holiday', 'leave_type', 'updated_at']
        read_only_fields = ['id', 'updated_at', 'is_holiday']

class ProfileViewSet(viewsets.ViewSet):
    """
    API endpoint to get current user info.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
class AttendanceRecordViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Android app to view or sync attendance records.
    """
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Users can only see their own records
        return AttendanceRecord.objects.filter(user=self.request.user).order_by('-date')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def sync_records(self, request):
        """
        Receives a list of records and updates them atomically using Last-Write-Wins.
        """
        records_data = request.data.get('records', [])
        synced_count = 0
        from django.db import transaction
        from django.utils.dateparse import parse_datetime

        with transaction.atomic():
            for data in records_data:
                date_val = data.get('date')
                if not date_val:
                    continue
                
                record, _ = AttendanceRecord.objects.get_or_create(
                    user=request.user, 
                    date=date_val
                )

                # Last-Write-Wins conflict protection
                client_updated_at = parse_datetime(data.get('updated_at', ''))
                if client_updated_at and record.updated_at:
                    if client_updated_at <= record.updated_at:
                        # Server has newer or same data, skip this record
                        continue
                
                serializer = AttendanceRecordSerializer(record, data=data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    synced_count += 1
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        return Response({'status': 'Sync successful', 'synced': synced_count}, status=status.HTTP_200_OK)
