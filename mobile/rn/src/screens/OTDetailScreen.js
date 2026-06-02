import React, { useState, useEffect } from 'react';
import {
  View,
  ScrollView,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
  Linking,
  SectionList,
} from 'react-native';
import { supabase } from '../config/supabaseConfig';

export default function OTDetailScreen({ route, navigation }) {
  const { otId } = route.params;
  const [otData, setOTData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOTDetail();
  }, []);

  const fetchOTDetail = async () => {
    try {
      setLoading(true);
      const { data, error } = await supabase
        .from('trabajo')
        .select(`
          *,
          clientes(nombre, rut, email, telefono, direccion),
          project_items(id, sku, descripcion, cantidad, item_type)
        `)
        .eq('id', otId)
        .single();

      if (error) {
        console.error('Error:', error);
      } else {
        setOTData(data);
      }
    } catch (error) {
      console.error('Error fetching OT detail:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1e3c72" />
      </View>
    );
  }

  if (!otData) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.errorText}>OT no encontrada</Text>
      </View>
    );
  }

  const cliente = otData.clientes?.[0];
  const items = otData.project_items || [];

  const callClient = () => {
    if (cliente?.telefono) {
      Linking.openURL(`tel:${cliente.telefono}`);
    }
  };

  const sections = [
    {
      title: '📋 Datos del Cliente',
      data: cliente ? [cliente] : [],
    },
    {
      title: '🛠️ Equipos a Instalar',
      data: items,
    },
  ];

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.backBtn}>← Volver</Text>
          </TouchableOpacity>
          <Text style={styles.headerTitle}>OT #{otData.numero}</Text>
          <View style={styles.spacer} />
        </View>

        {/* Cliente */}
        {cliente && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>👤 Cliente</Text>
            <View style={styles.card}>
              <Text style={styles.clientName}>{cliente.nombre}</Text>
              {cliente.rut && <Text style={styles.label}>RUT: {cliente.rut}</Text>}
              {cliente.direccion && (
                <Text style={styles.label}>📍 {cliente.direccion}</Text>
              )}
              {cliente.email && (
                <Text style={styles.label}>📧 {cliente.email}</Text>
              )}

              {cliente.telefono && (
                <TouchableOpacity
                  style={styles.callButton}
                  onPress={callClient}
                >
                  <Text style={styles.callButtonText}>📞 Llamar: {cliente.telefono}</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        )}

        {/* Descripción */}
        {otData.descripcion && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>📝 Descripción</Text>
            <View style={styles.card}>
              <Text style={styles.description}>{otData.descripcion}</Text>
            </View>
          </View>
        )}

        {/* Equipos */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>🛠️ Equipos a Instalar</Text>
          {items.length === 0 ? (
            <View style={styles.card}>
              <Text style={styles.emptyText}>Sin equipos asignados</Text>
            </View>
          ) : (
            items.map((item) => (
              <View key={item.id} style={styles.equipoCard}>
                <Text style={styles.equipoName}>{item.descripcion}</Text>
                <Text style={styles.equipoSKU}>SKU: {item.sku}</Text>
                <Text style={styles.equipoQty}>Cantidad: {item.cantidad}</Text>
              </View>
            ))
          )}
        </View>

        {/* Botón Iniciar */}
        <TouchableOpacity
          style={styles.startButton}
          onPress={() =>
            navigation.navigate('Execution', { otId: otData.id })
          }
        >
          <Text style={styles.startButtonText}>▶️ Iniciar Trabajo</Text>
        </TouchableOpacity>

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
  scrollView: {
    flex: 1,
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
    marginVertical: 10,
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
    borderLeftColor: '#3b82f6',
  },
  clientName: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: 8,
  },
  label: {
    fontSize: 14,
    color: '#6b7280',
    marginVertical: 4,
  },
  description: {
    fontSize: 14,
    color: '#4b5563',
    lineHeight: 20,
  },
  callButton: {
    marginTop: 12,
    backgroundColor: '#10b981',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  callButtonText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 14,
  },
  equipoCard: {
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    borderLeftWidth: 4,
    borderLeftColor: '#f59e0b',
  },
  equipoName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
  },
  equipoSKU: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 4,
  },
  equipoQty: {
    fontSize: 13,
    color: '#1e40af',
    fontWeight: '600',
    marginTop: 4,
  },
  startButton: {
    marginHorizontal: 15,
    marginVertical: 15,
    backgroundColor: '#1e3c72',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  startButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  emptyText: {
    fontSize: 14,
    color: '#9ca3af',
    textAlign: 'center',
  },
  errorText: {
    fontSize: 16,
    color: '#ef4444',
  },
});
