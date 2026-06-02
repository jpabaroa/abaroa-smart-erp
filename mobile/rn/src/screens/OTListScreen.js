import React, { useState, useEffect } from 'react';
import {
  View,
  FlatList,
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  SafeAreaView,
} from 'react-native';
import { supabase } from '../config/supabaseConfig';

export default function OTListScreen({ navigation }) {
  const [otList, setOTList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchOTList();
  }, []);

  const fetchOTList = async () => {
    try {
      setLoading(true);
      const { data, error } = await supabase
        .from('trabajo')
        .select(`
          id,
          numero,
          estado,
          fecha_creacion,
          descripcion,
          cliente_id,
          clientes(nombre, telefono, direccion)
        `)
        .in('estado', ['pendiente', 'en_progreso'])
        .order('fecha_creacion', { ascending: false })
        .limit(50);

      if (error) {
        console.error('Error:', error);
      } else {
        setOTList(data || []);
      }
    } catch (error) {
      console.error('Error fetching OT:', error);
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchOTList();
    setRefreshing(false);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'pendiente':
        return '#f59e0b';
      case 'en_progreso':
        return '#3b82f6';
      case 'completada':
        return '#10b981';
      default:
        return '#6b7280';
    }
  };

  const renderOTItem = ({ item }) => {
    const cliente = item.clientes?.[0];
    return (
      <TouchableOpacity
        style={styles.card}
        onPress={() => navigation.navigate('OTDetail', { otId: item.id })}
      >
        <View style={styles.cardHeader}>
          <Text style={styles.otNumber}>OT #{item.numero}</Text>
          <View
            style={[
              styles.statusBadge,
              { backgroundColor: getStatusColor(item.estado) },
            ]}
          >
            <Text style={styles.statusText}>{item.estado}</Text>
          </View>
        </View>

        {cliente && (
          <>
            <Text style={styles.clientName}>👤 {cliente.nombre}</Text>
            {cliente.direccion && (
              <Text style={styles.address}>📍 {cliente.direccion}</Text>
            )}
            {cliente.telefono && (
              <TouchableOpacity>
                <Text style={styles.phone}>📞 {cliente.telefono}</Text>
              </TouchableOpacity>
            )}
          </>
        )}

        {item.descripcion && (
          <Text style={styles.description}>{item.descripcion}</Text>
        )}

        <Text style={styles.date}>
          {new Date(item.fecha_creacion).toLocaleDateString()}
        </Text>
      </TouchableOpacity>
    );
  };

  if (loading && !refreshing) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1e3c72" />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>📋 OT del Día</Text>
        <TouchableOpacity onPress={() => fetchOTList()}>
          <Text style={styles.refreshBtn}>🔄</Text>
        </TouchableOpacity>
      </View>

      {otList.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>Sin OT asignadas</Text>
        </View>
      ) : (
        <FlatList
          data={otList}
          renderItem={renderOTItem}
          keyExtractor={(item) => item.id.toString()}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        />
      )}
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 15,
    paddingVertical: 15,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  refreshBtn: {
    fontSize: 20,
  },
  listContent: {
    padding: 15,
    gap: 10,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 15,
    borderLeftWidth: 4,
    borderLeftColor: '#3b82f6',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
    elevation: 3,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  otNumber: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  clientName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 5,
  },
  address: {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 4,
  },
  phone: {
    fontSize: 13,
    color: '#2563eb',
    marginBottom: 8,
  },
  description: {
    fontSize: 13,
    color: '#6b7280',
    fontStyle: 'italic',
    marginVertical: 8,
  },
  date: {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 8,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 16,
    color: '#9ca3af',
  },
});
