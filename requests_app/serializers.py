from rest_framework import serializers
from .models import DocumentRequest, DocumentType

class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = '__all__'

class RequestSerializer(serializers.ModelSerializer):
    doc_name = serializers.CharField(source='document_type.name', read_only=True)
    class Meta:
        model = DocumentRequest
        fields = ['id', 'doc_name', 'status', 'delivery_method', 'tracking_number', 'created_at']