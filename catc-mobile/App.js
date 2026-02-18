import React, { useState, useEffect } from 'react';
import { 
  StyleSheet, Text, View, TextInput, TouchableOpacity, 
  FlatList, SafeAreaView, Alert, ActivityIndicator 
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';

const BASE_URL = 'http://192.168.0.146:8000/api'; // YOUR IP

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [step, setStep] = useState(1); // 1: ID, 2: OTP, 3: Dashboard
  const [studentId, setStudentId] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);

  // Check if already logged in on launch
  useEffect(() => {
    checkLoginStatus();
  }, []);

  const checkLoginStatus = async () => {
    const token = await AsyncStorage.getItem('userToken');
    if (token) {
      setIsLoggedIn(true);
      fetchDashboard(token);
    }
  };

  const handleSendOTP = async () => {
    setLoading(true);
    try {
      await axios.post(`${BASE_URL}/login/`, { student_id: studentId });
      setStep(2);
      Alert.alert("OTP Sent", "Please check your email/SMS.");
    } catch (err) {
      Alert.alert("Error", "Student ID not found.");
    }
    setLoading(false);
  };

  const handleVerifyOTP = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${BASE_URL}/verify/`, { 
        student_id: studentId, 
        otp_code: otpCode 
      });
      await AsyncStorage.setItem('userToken', res.data.access);
      setIsLoggedIn(true);
      fetchDashboard(res.data.access);
    } catch (err) {
      Alert.alert("Error", "Invalid OTP code.");
    }
    setLoading(false);
  };

  const fetchDashboard = async (token) => {
    try {
      const res = await axios.get(`${BASE_URL}/dashboard/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setRequests(res.data);
    } catch (err) {
      handleLogout();
    }
  };

  const handleLogout = async () => {
    await AsyncStorage.clear();
    setIsLoggedIn(false);
    setStep(1);
    setStudentId('');
    setOtpCode('');
  };

  // --- UI COMPONENTS ---

  if (!isLoggedIn) {
    return (
      <View style={styles.loginContainer}>
        <Text style={styles.logoText}>CATC Portal</Text>
        
        {step === 1 ? (
          <View style={styles.inputBox}>
            <Text style={styles.label}>Enter Student ID</Text>
            <TextInput 
              style={styles.input} 
              placeholder="S000000" 
              value={studentId} 
              onChangeText={setStudentId}
              autoCapitalize="characters"
            />
            <TouchableOpacity style={styles.button} onPress={handleSendOTP}>
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>NEXT</Text>}
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.inputBox}>
            <Text style={styles.label}>Enter 6-Digit OTP</Text>
            <TextInput 
              style={styles.input} 
              placeholder="000000" 
              keyboardType="numeric"
              value={otpCode} 
              onChangeText={setOtpCode}
            />
            <TouchableOpacity style={[styles.button, {backgroundColor: '#28a745'}]} onPress={handleVerifyOTP}>
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>VERIFY</Text>}
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setStep(1)}>
              <Text style={styles.backLink}>Try different ID</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    );
  }

  // DASHBOARD VIEW
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>My Requests</Text>
        <TouchableOpacity onPress={handleLogout}>
          <Text style={{color: '#fff', fontWeight: 'bold'}}>Logout</Text>
        </TouchableOpacity>
      </View>
      <FlatList
        data={requests}
        keyExtractor={item => item.id.toString()}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.docName}>{item.doc_name}</Text>
            <Text style={{color: '#0d6efd', fontWeight: 'bold'}}>{item.status}</Text>
          </View>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  loginContainer: { flex: 1, justifyContent: 'center', padding: 30, backgroundColor: '#0d6efd' },
  logoText: { fontSize: 32, fontWeight: 'bold', color: '#fff', textAlign: 'center', marginBottom: 40 },
  inputBox: { backgroundColor: '#fff', padding: 25, borderRadius: 15, elevation: 10 },
  label: { fontSize: 14, color: '#666', marginBottom: 10, fontWeight: 'bold' },
  input: { borderBottomWidth: 2, borderBottomColor: '#0d6efd', fontSize: 18, marginBottom: 20, padding: 5 },
  button: { backgroundColor: '#0d6efd', padding: 15, borderRadius: 8, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },
  backLink: { textAlign: 'center', marginTop: 15, color: '#666' },
  container: { flex: 1, backgroundColor: '#f8f9fa' },
  header: { backgroundColor: '#0d6efd', padding: 20, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  headerTitle: { color: '#fff', fontSize: 20, fontWeight: 'bold' },
  card: { backgroundColor: '#fff', margin: 10, padding: 15, borderRadius: 10, elevation: 2 },
  docName: { fontSize: 16, fontWeight: 'bold' }
});