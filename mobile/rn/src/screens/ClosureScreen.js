import React, { useRef, useState } from 'react';
import {
  View,
  ScrollView,
  Text,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
  TextInput,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { supabase } from '../config/supabaseConfig';

export default function ClosureScreen({ route, navigation }) {
  const { otId } = route.params;
  const signatureRef = useRef(null);
  const [clientName, setClientName] = useState('');
  const [observations, setObservations] = useState('');
  const [signature, setSignature] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSignature = () => {
    // Placeholder - En producción usar react-native-signature-canvas
    setSignature('✓ Firma registrada');
    Alert.alert('✓', 'Firma del cliente registrada');
  };

  const completeOT = async () => {
    if (!clientName.trim()) {
      Alert.alert('Error', 'Por favor ingresa el nombre del cliente');
      return;
    }

    if (!signature) {
      Alert.alert('Error', 'Por favor obtén la firma del cliente');
      return;
    }

    try {
      setSaving(true);

      // Update OT as completed
      const { error } = await supabase
        .from('trabajo')
        .update({
          estado: 'completada',
          fecha_completacion: new Date().toISOString(),
          observaciones: observations,
          firma_cliente: clientName,
        })
        .eq('id', otId);

      if (error) throw error;

      Alert.alert('✓ Éxito', 'OT completada correctamente', [
        {
          text: 'OK',
          onPress: () => navigation.replace('OTList'),
        },
      ]);
    } catch (error) {
      console.error('Error:', error);
      Alert.alert('Error', 'No se pudo completar la OT');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.backBtn}>← Volver</Text>
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Cierre de OT</Text>
          <View style={styles.spacer} />
        </View>

        {/* Resumen */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📊 Resumen de Trabajo</Text>
          <View style={styles.card}>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>OT Número:</Text>
              <Text style={styles.summaryValue}>#{otId}</Text>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Estado:</Text>
              <View style={[styles.badge, styles.badgeComplete]}>
                <Text style={styles.badgeText}>Completada</Text>
              </View>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Fecha:</Text>
              <Text style={styles.summaryValue}>
                {new Date().toLocaleDateString()}
              </Text>
            </View>
          </View>
        </View>

        {/* Firma del Cliente */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>✍️ Firma del Cliente</Text>
          <View style={styles.signatureBox}>
            <TouchableOpacity
              style={styles.signatureButton}
              onPress={handleSignature}
            >
              <Text style={styles.signatureButtonText}>
                {signature ? '✓ Firma Capturada' : '📱 Obtener Firma'}
              </Text>
            </TouchableOpacity>
            {signature && (
              <View style={styles.signaturePreview}>
                <Text style={styles.signatureText}>{signature}</Text>
              </View>
            )}
          </View>
        </View>

        {/* Nombre del Cliente */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>👤 Nombre del Cliente</Text>
          <TextInput
            style={styles.input}
            placeholder="Nombre y apellido"
            value={clientName}
            onChangeText={setClientName}
            editable={!saving}
          />
        </View>

        {/* Observaciones */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📝 Observaciones</Text>
          <TextInput
            style={[styles.input, styles.largeInput]}
            placeholder="Problemas encontrados, recomendaciones, etc."
            multiline
            numberOfLines={4}
            value={observations}
            onChangeText={setObservations}
            editable={!saving}
            textAlignVertical="top"
          />
        </View>

        {/* Checklist Final */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>✓ Checklist Final</Text>
          <View style={styles.checklistFinal}>
            <View style={styles.checklistRow}>
              <Text style={styles.checkmark}>✓</Text>
              <Text style={styles.checklistText}>
                Todos los equipos instalados
              </Text>
            </View>
            <View style={styles.checklistRow}>
              <Text style={styles.checkmark}>✓</Text>
              <Text style={styles.checklistText}>Pruebas realizadas</Text>
            </View>
            <View style={styles.checklistRow}>
              <Text style={styles.checkmark}>✓</Text>
              <Text style={styles.checklistText}>Cliente satisfecho</Text>
            </View>
            <View style={styles.checklistRow}>
              <Text style={styles.checkmark}>✓</Text>
              <Text style={styles.checklistText}>Área limpia</Text>
            </View>
          </View>
        </View>

        {/* Botones de acción */}
        <View style={styles.buttonContainer}>
          <TouchableOpacity
            style={[styles.button, styles.completeButton, saving && styles.buttonDisabled]}
            onPress={completeOT}
            disabled={saving}
          >
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>✓ Completar OT</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.button, styles.cancelButton]}
            onPress={() => navigation.goBack()}
            disabled={saving}
          >
            <Text style={styles.buttonText}>← Volver</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: 30 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8f9fa',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 15,
    paddingVertical: 15,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  backBtn: {
    fontSize: 14,
    color: '#2563eb',
    fontWeight: '600',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  spacer: {
    width: 50,
  },
  section: {
    marginHorizontal: 15,
    marginVertical: 12,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 10,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 15,
    borderLeftWidth: 4,
    borderLeftColor: '#10b981',
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  summaryLabel: {
    fontSize: 14,
    color: '#6b7280',
    fontWeight: '600',
  },
  summaryValue: {
    fontSize: 14,
    color: '#1f2937',
    fontWeight: '600',
  },
  badge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  badgeComplete: {
    backgroundColor: '#d1fae5',
  },
  badgeText: {
    color: '#065f46',
    fontSize: 12,
    fontWeight: '600',
  },
  signatureBox: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 15,
    borderWidth: 2,
    borderColor: '#e5e7eb',
    borderStyle: 'dashed',
  },
  signatureButton: {
    backgroundColor: '#3b82f6',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  signatureButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  signaturePreview: {
    marginTop: 12,
    padding: 12,
    backgroundColor: '#f9fafb',
    borderRadius: 8,
    alignItems: 'center',
  },
  signatureText: {
    fontSize: 16,
    color: '#10b981',
    fontWeight: '700',
  },
  input: {
    backgroundColor: '#fff',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: '#1f2937',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  largeInput: {
    minHeight: 100,
    textAlignVertical: 'top',
  },
  checklistFinal: {
    backgroundColor: '#fff',
    borderRadius: 10,
    paddingVertical: 12,
    borderLeftWidth: 4,
    borderLeftColor: '#10b981',
  },
  checklistRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
    paddingVertical: 8,
  },
  checkmark: {
    fontSize: 18,
    color: '#10b981',
    marginRight: 12,
    fontWeight: '700',
  },
  checklistText: {
    fontSize: 14,
    color: '#1f2937',
  },
  buttonContainer: {
    marginHorizontal: 15,
    marginVertical: 15,
    gap: 10,
  },
  button: {
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  completeButton: {
    backgroundColor: '#10b981',
  },
  cancelButton: {
    backgroundColor: '#6b7280',
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
});
