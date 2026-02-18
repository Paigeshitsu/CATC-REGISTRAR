import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, StyleSheet, TouchableOpacity } from 'react-native';
import axios from 'axios';

export default function Dashboard() {
  const [requests, setRequests] = useState([]);

  useEffect(() => {
    // Replace with your PC's IP address (e.g., 192.168.1.5)
    axios.get('http://YOUR_PC_IP:8000/api/dashboard/', {
      headers: { Authorization: `Bearer YOUR_JWT_TOKEN` }
    })
    .then(res => setRequests(res.data))
    .catch(err => console.log(err));
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>CATC Document Portal</Text>
      <FlatList
        data={requests}
        keyExtractor={item => item.id.toString()}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.docName}>{item.doc_name}</Text>
            <Text style={styles.status}>{item.status}</Text>
            {item.tracking_number && <Text>LBC: {item.tracking_number}</Text>}
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingTop: 50, paddingHorizontal: 20, backgroundColor: '#f8f9fa' },
  title: { fontSize: 22, fontWeight: 'bold', marginBottom: 20, color: '#0d6efd' },
  card: { backgroundColor: '#fff', padding: 15, borderRadius: 10, marginBottom: 10, elevation: 3 },
  docName: { fontWeight: 'bold', fontSize: 16 },
  status: { color: 'green', marginTop: 5 }
});