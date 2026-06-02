import React, { useState, useEffect } from 'react';
import {
  View,
  ScrollView,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
  CheckBox,
  TextInput,
  FlatList,
} from 'react-native';
import { supabase } from '../config/supabaseConfig';

export default function ExecutionScreen({ route, navigation }) {
  const { otId } = route.params;
  const [otData, setOTData] = useState(null);
  const [checklist, setChecklist] = useState([]);
  const [equipoUsado, setEquipoUsado] = useState([]);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    fetchExecutionData();
  }, []);

  const fetchExecutionData = async () => {
    try {
      setLoading(true);

      // OT data
      const { data: otRes, error: otErr } = await supabase
        .from('trabajo')
        .select('*, project_items(id, sku, descripcion, cantidad)')
        .eq('id', otId)
        .single();

      if (otErr) throw otErr;
      setOTData(otRes);

      // Checklist
      const { data: checklistRes, error: checklistErr } = await supabase
        .from('checklist')
        .select('*')
        .eq('ot_id', otId)
        .order('orden', { ascending: true });

      if (checklistErr) throw checklistErr;
      setChecklist(
        checklistRes.map((item) => ({
          ...item,
          completado: false,
          nota: '',
        }))
      );

      // Initialize equipo usado
      if (otRes.project_items) {
        setEquipoUsado(
          otRes.project_items.map((item) => ({
            ...item,
            cantidad_instalada: 0,
          }))
        );
      }
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleChecklistItem = (id) => {
    setChecklist(
      checklist.map((item) =>
        item.id === id ? { ...item, completado: !item.completado } : item
      )
    );
    updateProgress();
  };

  const updateChecklistNote = (id, nota) => {
    setChecklist(
      checklist.map((item) =>
        item.id === id ? { ...item, nota } : item
      )
    );
  };

  const updateEquipoQuantity = (id, cantidad) => {
    setEquipoUsado(
      equipoUsado.map((item) =>
        item.id === id
          ? { ...item, cantidad_instalada: parseInt(cantidad) || 0 }
          : item
      )
    );
  };

  const updateProgress = () => {
    if (checklist.length === 0) return;
    const completed = checklist.filter((item) => item.completado).length;
    setProgress((completed / checklist.length) * 100);
  };

  const saveProgress = async () => {
    try {
      setSaving(true);

      // Update checklist items
      for (const item of checklist) {
        if (item.completado) {
          await supabase
            .from('checklist')
            .update({
              completado: true,
              nota: item.nota,
            })
            .eq('id', item.id);
        }
      }

      // Update OT status
      await supabase
        .from('trabajo')
        .update({ estado: 'en_progreso' })
        .eq('id', otId);

      alert('Progreso guardado');
    } catch (error) {
      console.error('Error saving:', error);
      alert('Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1e3c72" />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView>
        {/* Header con progreso */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.backBtn}>← Volver</Text>
          </TouchableOpacity>
          <View style={styles.progressContainer}>
            <Text style={styles.progressText}>{Math.round(progress)}%</Text>
            <View style={styles.progressBar}>
              <View
                style={[
                  styles.progressFill,
                  { width: `${progress}%` },
                ]}
              />
            </View>
          </View>
        </View>

        {/* Checklist */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>✓ Checklist de Instalación</Text>
          {checklist.length === 0 ? (
            <Text style={styles.emptyText}>Sin checklist</Text>
          ) : (
            checklist.map((item) => (
              <View key={item.id} style={styles.checklistItem}>
                <TouchableOpacity
                  style={styles.checkbox}
                  onPress={() => toggleChecklistItem(item.id)}
                >
                  <Text style={styles.checkboxText}>
                    {item.completado ? '✓' : '○'}
                  </Text>
                </TouchableOpacity>
                <View style={styles.checklistContent}>
                  <Text
                    style={[
                      styles.checklistText,
                      item.completado && styles.checklistTextCompleted,
                    ]}
                  >
                    {item.paso}
                  </Text>
                  {item.completado && (
                    <TextInput
                      style={styles.noteInput}
                      placeholder="Nota (opcional)"
                      value={item.nota}
                      onChangeText={(text) =>
                        updateChecklistNote(item.id, text)
                      }
                      multiline
                    />
                  )}
                </View>
              </View>
            ))
          )}
        </View>

        {/* Equipos Instalados */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>🛠️ Equipos Instalados</Text>
          {equipoUsado.length === 0 ? (
            <Text style={styles.emptyText}>Sin equipos</Text>
          ) : (
            equipoUsado.map((item) => (
              <View key={item.id} style={styles.equipoItem}>
                <Text style={styles.equipoName}>{item.descripcion}</Text>
                <View style={styles.equipoControls}>
                  <Text style={styles.equipoLabel}>
                    Cantidad: {item.cantidad}
                  </Text>
                  <TextInput
                    style={styles.equipoInput}
                    placeholder="Cantidad instalada"
                    keyboardType="numeric"
                    value={item.cantidad_instalada.toString()}
                    onChangeText={(text) =>
                      updateEquipoQuantity(item.id, text)
                    }
                  />
                </View>
              </View>
            ))
          )}
        </View>

        {/* Notas generales */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📝 Notas</Text>
          <TextInput
            style={styles.notesInput}
            placeholder="Agrega notas sobre la instalación..."
            multiline
            numberOfLines={4}
            value={notes}
            onChangeText={setNotes}
          />
        </View>

        {/* Botones */}
        <View style={styles.buttonContainer}>
          <TouchableOpacity
            style={[styles.button, saving && styles.buttonDisabled]}
            onPress={saveProgress}
            disabled={saving}
          >
            <Text style={styles.buttonText}>
              {saving ? '💾 Guardando...' : '💾 Guardar Progreso'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.button, styles.nextButton]}
            onPress={() =>
              navigation.navigate('Closure', { otId })
            }
          >
            <Text style={styles.buttonText}>➜ Ir a Cierre</Text>
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
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
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
    marginBottom: 10,
  },
  progressContainer: {
    gap: 8,
  },
  progressText: {
    fontSize: 12,
    color: '#6b7280',
    fontWeight: '600',
  },
  progressBar: {
    height: 6,
    backgroundColor: '#e5e7eb',
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#10b981',
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
  checklistItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#fff',
    padding: 12,
    marginBottom: 8,
    borderRadius: 8,
    borderLeftWidth: 3,
    borderLeftColor: '#3b82f6',
  },
  checkbox: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#f3f4f6',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  checkboxText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#9ca3af',
  },
  checklistContent: {
    flex: 1,
  },
  checklistText: {
    fontSize: 14,
    color: '#1f2937',
    fontWeight: '500',
  },
  checklistTextCompleted: {
    color: '#10b981',
    textDecorationLine: 'line-through',
  },
  noteInput: {
    marginTop: 8,
    backgroundColor: '#f9fafb',
    borderRadius: 6,
    padding: 8,
    fontSize: 12,
    color: '#6b7280',
    minHeight: 60,
  },
  equipoItem: {
    backgroundColor: '#fff',
    padding: 12,
    marginBottom: 8,
    borderRadius: 8,
    borderLeftWidth: 3,
    borderLeftColor: '#f59e0b',
  },
  equipoName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 8,
  },
  equipoControls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  equipoLabel: {
    fontSize: 12,
    color: '#6b7280',
  },
  equipoInput: {
    flex: 1,
    backgroundColor: '#f9fafb',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 6,
    fontSize: 14,
    color: '#1f2937',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  notesInput: {
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    color: '#1f2937',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    textAlignVertical: 'top',
  },
  buttonContainer: {
    marginHorizontal: 15,
    marginVertical: 15,
    gap: 10,
  },
  button: {
    backgroundColor: '#1e3c72',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  nextButton: {
    backgroundColor: '#10b981',
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  emptyText: {
    fontSize: 14,
    color: '#9ca3af',
    textAlign: 'center',
    padding: 15,
  },
});
